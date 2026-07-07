import 'dart:async';
import 'dart:isolate';
import 'dart:typed_data';

import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';

import 'offline_recognition_service.dart';

class OfflineRecognitionIsolateService {
  Isolate? _isolate;
  SendPort? _workerSendPort;
  bool _initialized = false;

  Future<void> init({
    required int tourId,
    required String modelAssetPath,
  }) async {
    if (_initialized) return;

    final bootstrapPort = ReceivePort();

    _isolate = await Isolate.spawn(
      _offlineRecognitionWorkerMain,
      bootstrapPort.sendPort,
      debugName: 'offline_recognition_worker',
    );

    _workerSendPort = await bootstrapPort.first as SendPort;
    bootstrapPort.close();

    final modelData = await rootBundle.load(modelAssetPath);
    final modelBytes = modelData.buffer.asUint8List();

    final appDir = await getApplicationDocumentsDirectory();
    final tourDirPath = '${appDir.path}/offline_tours_data/tour_$tourId';

    final response = await _sendMessage({
      'type': 'init',
      'tourId': tourId,
      'tourDirPath': tourDirPath,
      'modelBytes': TransferableTypedData.fromList([modelBytes]),
    });

    if (response is Map && response['ok'] == true) {
      _initialized = true;
      return;
    }

    throw Exception(response is Map ? response['error'] : 'Worker init failed');
  }

  Future<int> matchFromImageBytes(
    Uint8List imageBytes, {
    int sensorOrientation = 0,
    bool useGeometry = false,
    double? queryLat,
    double? queryLon,
    double? queryAccuracyM,
  }) async {
    if (!_initialized || _workerSendPort == null) {
      throw Exception('Offline recognition isolate not initialized');
    }

    final response = await _sendMessage({
      'type': 'match',
      'imageBytes': TransferableTypedData.fromList([imageBytes]),
      'sensorOrientation': sensorOrientation,
      'useGeometry': useGeometry,
      'queryLat': queryLat,
      'queryLon': queryLon,
      'queryAccuracyM': queryAccuracyM,
    });

    if (response is Map && response['ok'] == true) {
      return (response['waypointId'] as num?)?.toInt() ?? -1;
    }

    throw Exception(
      response is Map ? response['error'] : 'Worker match failed',
    );
  }

  Future<dynamic> _sendMessage(Map<String, dynamic> message) async {
    final sendPort = _workerSendPort;

    if (sendPort == null) {
      throw Exception('Offline recognition worker is not available');
    }

    final responsePort = ReceivePort();

    sendPort.send({...message, 'replyTo': responsePort.sendPort});

    try {
      return await responsePort.first.timeout(const Duration(seconds: 60));
    } finally {
      responsePort.close();
    }
  }

  Future<void> dispose() async {
    if (_workerSendPort != null) {
      try {
        await _sendMessage({'type': 'dispose'});
      } catch (_) {}
    }

    _isolate?.kill(priority: Isolate.immediate);
    _isolate = null;
    _workerSendPort = null;
    _initialized = false;
  }
}

void _offlineRecognitionWorkerMain(SendPort mainSendPort) {
  final commandPort = ReceivePort();
  mainSendPort.send(commandPort.sendPort);

  OfflineRecognitionService? recognitionService;

  commandPort.listen((message) async {
    if (message is! Map) return;

    final replyTo = message['replyTo'] as SendPort?;

    if (replyTo == null) return;

    try {
      final type = message['type'];

      switch (type) {
        case 'init':
          final tourId = (message['tourId'] as num).toInt();
          final tourDirPath = message['tourDirPath'] as String;

          final modelTransferable =
              message['modelBytes'] as TransferableTypedData;
          final modelBytes = modelTransferable.materialize().asUint8List();

          recognitionService = OfflineRecognitionService();

          await recognitionService!.initEmbedderFromBytes(modelBytes);

          await recognitionService!.initIndexForTourDirectory(
            tourId,
            tourDirPath,
          );

          replyTo.send({'ok': true});
          break;

        case 'match':
          final service = recognitionService;

          if (service == null) {
            throw Exception('Recognition service not initialized in worker');
          }

          final imageTransferable =
              message['imageBytes'] as TransferableTypedData;
          final imageBytes = imageTransferable.materialize().asUint8List();

          final waypointId = await service.matchFromImageBytes(
            imageBytes,
            sensorOrientation:
                (message['sensorOrientation'] as num?)?.toInt() ?? 0,
            useGeometry: message['useGeometry'] == true,
            queryLat: (message['queryLat'] as num?)?.toDouble(),
            queryLon: (message['queryLon'] as num?)?.toDouble(),
            queryAccuracyM: (message['queryAccuracyM'] as num?)?.toDouble(),
          );

          replyTo.send({'ok': true, 'waypointId': waypointId});
          break;

        case 'dispose':
          recognitionService?.dispose();
          recognitionService = null;

          replyTo.send({'ok': true});
          break;

        default:
          throw Exception('Unknown worker message type: $type');
      }
    } catch (e, stackTrace) {
      replyTo.send({
        'ok': false,
        'error': e.toString(),
        'stackTrace': stackTrace.toString(),
      });
    }
  });
}
