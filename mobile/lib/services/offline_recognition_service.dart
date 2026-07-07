import 'dart:math' as math;
import 'dart:convert';
import 'dart:typed_data';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show rootBundle;
import 'package:image/image.dart' as img;
import 'package:tflite_flutter/tflite_flutter.dart';
import 'package:opencv_dart/opencv_dart.dart' as cv;
import 'package:path_provider/path_provider.dart';
import "package:camera/camera.dart";

class OfflineRecognitionService {

  Interpreter? _embedder;
  int? _modelOutputDim;
  final int dim; // dimensione embedding (es. 2048 o 1280)
  final int inputSize;

  //CONSTANTS FOR MATCHING AND SCORING
  static const double _similarityThreshold = 0.58;

  static const double _directAcceptThreshold = 0.76;
  static const double _directAcceptMargin = 0.10;
  static const double _directAcceptMinVoteRatio = 0.60;

  static const double _softAcceptThreshold = 0.64;
  static const double _softAcceptMargin = 0.055;
  static const double _softAcceptMinVoteRatio = 0.40;

  static const double _originalMinForDirect = 0.56;
  static const double _originalMinForSoft = 0.50;
  static const double _ambiguousMargin = 0.045;

  static const int _topItemsForWaypointScore = 3;
  static const int _topWaypointsToVerify = 5;

  static const int _defaultInliersThreshold = 8;
  static const int _topMatchesForRansac = 120;
  static const double _geometryStrongRatio = 0.12;
  static const int _geometryStrongInliers = 14;
  static const double _geometryRescueMinScore = 0.56;
  static const double _geometryRescueMinMargin = 0.015;

  static const double _gpsPriorWeight = 0.20;
  static const double _gpsDefaultRadiusM = 75.0;
  static const double _gpsDefaultAccuracyM = 30.0;
  static const double _gpsMinConfidence = 0.25;
  static const double _gpsFarMultiplier = 4.0;
  static const double _gpsMinFarDistanceM = 250.0;


  final List<List<double>> _dbEmbeddings = [];
  final List<int> _imgWpIds = [];
  final List<int> _descRows = [];
  final List<Uint8List> _descBytes = [];
  final List<List<List<double>>> _kpCoords = [];
  bool _jsonIndexLoaded = false;

  final Map<int, List<int>> _wpToImageIndexes = {};
  final List<String> _sourceImagePaths = [];
  final List<String> _variantNames = [];
  final List<double> _variantWeights = [];
  final List<double?> _gpsLat = [];
  final List<double?> _gpsLon = [];
  final List<double?> _gpsRadiusM = [];


  OfflineRecognitionService({this.dim = 1280, this.inputSize = 224});

  //Load the TFLite model from asset
  Future<void> initEmbedderFromAsset(String assetPath) async {
    try {
      final modelData = await rootBundle.load(assetPath);
      // _embedder = await Interpreter.fromBuffer(modelData.buffer.asUint8List());
      // final outputShape = _embedder!.getOutputTensor(0).shape;
      // _modelOutputDim = outputShape.isNotEmpty ? outputShape.last : dim;
      await initEmbedderFromBytes(modelData.buffer.asUint8List());
      debugPrint('Interpreter loaded successfully from asset: $assetPath (output dim $_modelOutputDim)');
    } catch (e) {
      debugPrint('Error loading interpreter from asset: $e');
      rethrow;
    }
  }

  Future<void> initEmbedderFromBytes(Uint8List modelBytes) async {
    try {
      _embedder = await Interpreter.fromBuffer(modelBytes);

      final outputShape = _embedder!.getOutputTensor(0).shape;
      _modelOutputDim = outputShape.isNotEmpty ? outputShape.last : dim;

      debugPrint(
        'Interpreter loaded successfully from bytes '
        '(output dim $_modelOutputDim)',
      );
    } catch (e) {
      debugPrint('Error loading interpreter from bytes: $e');
      rethrow;
    }
  }

  List<double> _alignEmbedding(List<double> emb) {
    final targetDim = _modelOutputDim ?? dim;
    if (emb.length == targetDim) return emb;

    if (emb.length > targetDim) {
      return emb.sublist(0, targetDim);
    }

    final aligned = List<double>.filled(targetDim, 0.0);
    for (var i = 0; i < emb.length && i < targetDim; i++) {
      aligned[i] = emb[i];
    }
    return aligned;
  }

  //Load the offline JSON index
  Future<void> initIndexForTour(int tourId) async {
    final appDir = await getApplicationDocumentsDirectory();
    final tourDirPath = '${appDir.path}/offline_tours_data/tour_$tourId';

    await initIndexForTourDirectory(tourId, tourDirPath);
  }

  Future<void> initIndexForTourDirectory(int tourId, String tourDirPath) async {

    final tourDir = Directory(tourDirPath);

    final indexJsonFile = File('${tourDir.path}/training_data.json');
    if (!await indexJsonFile.exists()) {
      debugPrint('Index JSON file not found for tour $tourId at ${indexJsonFile.path}');
      return;
    }

    final tourDataFile = File('${tourDir.path}/tour_data.json');
    if (!await tourDataFile.exists()) {
      debugPrint('Tour data JSON file not found for tour $tourId at ${tourDataFile.path}');
      return;
    }

    final tourData = jsonDecode(await tourDataFile.readAsString()) as Map<String, dynamic>;
    final Map<String, int> nameToId = {};
    final wps = (tourData['waypoints'] as List?) ?? [];
    for (final w in wps) {
      final id = (w['id'] as num).toInt();
      final title = (w['title'] ?? '').toString();
      if (title.isNotEmpty) nameToId[title] = id;
    }
    final subTours = (tourData['sub_tours'] as List?) ?? [];
    for (final st in subTours) {
      final wps = (st['waypoints'] as List?) ?? [];
      for (final w in wps) {
        final id = (w['id'] as num).toInt();
        final title = (w['title'] ?? '').toString();
        if (title.isNotEmpty) nameToId[title] = id;
      }
    }


    _dbEmbeddings.clear();
    _imgWpIds.clear();
    _descRows.clear();
    _descBytes.clear();
    _kpCoords.clear();
    _sourceImagePaths.clear();
    _variantNames.clear();
    _variantWeights.clear();
    _gpsLat.clear();
    _gpsLon.clear();
    _gpsRadiusM.clear();
    _wpToImageIndexes.clear();

    final List<dynamic> items = jsonDecode(await indexJsonFile.readAsString()) as List<dynamic>;
    for (final it in items) {
      final m = it as Map<String, dynamic>;
      final String wpName = m["waypoint_name"]?.toString() ?? '';
      final int wpId = nameToId[wpName] ?? -1;

      final sourceImagePath = (m["source_image_path"] ?? m["image_path"] ?? "") as String;
      final variantName = (m["variant_name"] ?? "original") as String;
      final variantWeight = (m["variant_weight"] as num?)?.toDouble() ?? 1.0;
      final gpsLat = (m["gps_lat"] as num?)?.toDouble();
      final gpsLon = (m["gps_lon"] as num?)?.toDouble();
      final gpsRadiusM = (m["gps_radius_m"] as num?)?.toDouble();


      final embList = (m["embedding"] as List).map((e) => (e as num).toDouble()).toList();
      final alignedEmb = _alignEmbedding(embList);
      final norm = math.sqrt(alignedEmb.fold<double>(0, (s,v) => s + v * v));
      final emb = norm >0 ? alignedEmb.map((e) => e / norm).toList() : alignedEmb;

      final kps = (m['keypoints'] as List?)?? const [];
      final coords = <List<double>>[];
      for (final k in kps) {
        final kk = k as List;
        final pt = kk[0] as List;
        coords.add([(pt[0] as num).toDouble(), (pt[1] as num).toDouble()]);
      }

      final rows = (m['desc_rows'] as num?)?.toInt() ?? 0;
      final cols = (m['desc_cols'] as num?)?.toInt() ?? 0;
      Uint8List bytes = Uint8List(0);
      if (rows > 0 && cols > 0) {
        final b64 = (m["descriptors_b64"] ?? '') as String;
        if (b64.isNotEmpty) {
          bytes = base64Decode(b64);
          if (bytes.length != rows * cols) {
            debugPrint('Warning: descriptor bytes length mismatch for waypoint $wpName');
            bytes = Uint8List(0);
          }
        }
      }

      if (emb.isNotEmpty && coords.length == rows){
        final imgIndex = _dbEmbeddings.length;
        _dbEmbeddings.add(emb);
        _imgWpIds.add(wpId);
        _descRows.add(rows);
        _descBytes.add(bytes);
        _kpCoords.add(coords.map((p) => [p[0], p[1]]).toList());
        _sourceImagePaths.add(sourceImagePath);
        _variantNames.add(variantName);
        _variantWeights.add(variantWeight);
        _gpsLat.add(gpsLat);
        _gpsLon.add(gpsLon);
        _gpsRadiusM.add(gpsRadiusM);

        if (wpId != -1) {
          _wpToImageIndexes.putIfAbsent(wpId, () => []).add(imgIndex);
        }
      }
    }

    // debugPrint("NAMETOID: ${nameToId}");

    if (_dbEmbeddings.isEmpty) {
      throw Exception("Indice offline vuoto o non valido per il tour $tourId");
    }
    _jsonIndexLoaded = true;
    debugPrint('Offline index loaded for tour $tourId with ${_dbEmbeddings.length} images.');
  }

  img.Image _preprocessImage(img.Image image) {
    final shortest = math.min(image.width, image.height);

    final scale = 256 / shortest;
    final resized = img.copyResize(
      image,
      width: (image.width * scale).round(),
      height: (image.height * scale).round(),
      interpolation: img.Interpolation.cubic,
    );
    // debugPrint("  [Dart] Resized shape: ${resized.width}x${resized.height}");

    // final cropX = ((resized.width - inputSize) / 2).round().clamp(0, resized.width - inputSize);
    // final cropY = ((resized.height - inputSize) / 2).round().clamp(0, resized.height - inputSize);
    final cropX = ((resized.width - inputSize) / 2).round();
    final cropY = ((resized.height - inputSize) / 2).round();


    return img.copyCrop(resized, x: cropX, y: cropY, width: inputSize, height: inputSize);
  }

  List<double> _extractEmbedding(img.Image image) {
    if (_embedder == null) throw Exception("Embedder not initialized");

    final processedImage = _preprocessImage(image);

    final pixels = inputSize * inputSize;
    final floatBuffer = Float32List(pixels * 3);

    // --- DEBUG LOGGING ---
    List<String> pixelLogs = [];
    for (int i = 0; i < 10; i++) {
      final pixel = processedImage.getPixel(i, 0);
      pixelLogs.add(
        "[${pixel.r.toInt()}, ${pixel.g.toInt()}, ${pixel.b.toInt()}]",
      );
    }
    // debugPrint("  [Dart] First 10 cropped RGB pixels:\n[${pixelLogs.join(', ')}]");

    // 3. Normalize
    int bufferIndex = 0;
    for (int y = 0; y < inputSize; y++) {
      for (int x = 0; x < inputSize; x++) {
        final pixel = processedImage.getPixel(x, y);
        floatBuffer[bufferIndex++] = pixel.r.toDouble();
        floatBuffer[bufferIndex++] = pixel.g.toDouble();
        floatBuffer[bufferIndex++] = pixel.b.toDouble();
      }
    }

    // --- DEBUG LOGGING ---
    // debugPrint(
    //   "  [Dart] First 30 normalized values:\n${floatBuffer.sublist(0, 30)}",
    // );

    // 4. Prepare Tensor
    // Reshape to [1, 224, 224, 3] for NHWC models
    final inputTensor = floatBuffer.reshape([1, inputSize, inputSize, 3]);

    final outputShape = _embedder!.getOutputTensor(0).shape;
    final outputBuffer = List.filled(
      outputShape.reduce((a, b) => a * b),
      0.0,
    ).reshape(outputShape);

    _embedder!.run(inputTensor, outputBuffer);

    // final embedding = (outputBuffer[0] as List).cast<double>();
    List<double> embedding = [];

    void flattenToDoubles(dynamic item) {
      if (item is List) {
        for (var subItem in item) {
          flattenToDoubles(subItem);
        }
      } else if (item is num) {
        embedding.add(item.toDouble());
      }
    }

    flattenToDoubles(outputBuffer);

    // Limita alla dimensione del modello se necessario
    final targetDim = _modelOutputDim ?? dim;
    if (embedding.length > targetDim) {
      embedding = embedding.sublist(0, targetDim);
    }

    // 5. L2 Normalize Embedding
    final n = math.sqrt(embedding.fold<double>(0, (s, e) => s + e * e));
    final normalizedEmbedding =
        n > 1e-6 ? embedding.map((e) => e / n).toList() : embedding;

    // debugPrint("  [Dart] Embedding norm: $n");
    // debugPrint(
    //   "  [Dart] First 10 embedding values:\n${normalizedEmbedding.sublist(0, 10)}",
    // );

    return normalizedEmbedding;
  }

  List<img.Image> _buildQueryViews(img.Image image) {
    final w = image.width;
    final h = image.height;

    img.Image crop(double l, double t, double r, double b) {
      final left = (w * l).toInt();
      final top = (h * t).toInt();
      final right = (w * r).toInt();
      final bottom = (h * b).toInt();

      final cropped = img.copyCrop(
        image,
        x: left,
        y: top,
        width: right - left,
        height: bottom - top,
      );
      return img.copyResize(cropped, width: w, height: h);
    }

    img.Image applyBrightness(img.Image src, double factor) {
      final copy = img.Image.from(src);
      return img.adjustColor(copy, brightness: factor - 1.0);
    }

    img.Image applyContrast(img.Image src, double factor) {
      final copy = img.Image.from(src);
      return img.adjustColor(copy, contrast: factor);
    }

    return [
      image, // center
      crop(0.10, 0.10, 0.90, 0.90),
      crop(0.00, 0.08, 0.85, 0.92),
      crop(0.15, 0.08, 1.00, 0.92),
      crop(0.08, 0.00, 0.92, 0.85),
      crop(0.08, 0.15, 0.92, 1.00),
      applyBrightness(image, 0.80),
      applyBrightness(image, 1.15),
      applyContrast(image, 0.85),
      applyContrast(image, 1.15),
    ];
  }

  List<double> _queryViewWeights() {
    return [
      1.00, // center
      0.98, // crop_center
      0.92, // crop_left
      0.92, // crop_right
      0.88, // crop_top
      0.88, // crop_bottom
      0.90, // brightness_down_q
      0.90, // brightness_up_q
      0.88, // contrast_down_q
      0.88, // contrast_up_q
    ];
  }

  double _cosine(List<double> a, List<double> b) {
    final len = math.min(a.length, b.length);
    double s = 0.0;
    for (int j = 0; j < len; j++) {
      s += a[j] * b[j];
    }
    return s;
  }

  double _clamp(double val, double min, double max) {
    return math.max(min, math.min(max, val));
  }

  double _haversineDistanceM(double lat1, double lon1, double lat2, double lon2) {
    const earthRadiusM = 6371000.0;

    final phi1 = lat1 * math.pi / 180.0;
    final phi2 = lat2 * math.pi / 180.0;
    final deltaPhi = (lat2 - lat1) * math.pi / 180.0;
    final deltaLambda = (lon2 - lon1) * math.pi / 180.0;

    final a =
      math.sin(deltaPhi / 2) * math.sin(deltaPhi / 2) +
      math.cos(phi1) * math.cos(phi2) *
          math.sin(deltaLambda / 2) * math.sin(deltaLambda / 2);

    final c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1 - a));
    return earthRadiusM * c;    
  }

  double _gpsConfidenceFromAccuracy(double? accuracyM) {
    final acc = math.max(accuracyM ?? _gpsDefaultAccuracyM, 1.0);
    final confidence = 1.0 - math.max(0.0, acc - 25.0) / 175.0;
    return _clamp(confidence, _gpsMinConfidence, 1.0);
  }

  Map<String, dynamic> _verifyWaypointGeometry(
    int waypointId,
    List<double> scores,
    Uint8List visionBytes, {
    int inliersThreshold = _defaultInliersThreshold,
    int topMatchesForRansac = _topMatchesForRansac,
    int maxRefs = 5,
  }) {
    final refs =
        (_wpToImageIndexes[waypointId] ?? const <int>[])
            .where((i) => _variantNames[i] == "original")
            .toList();

    if (refs.isEmpty) {
      return {"passed": false, "strong": false, "inliers": 0, "ratio": 0.0};
    }

    refs.sort((a, b) => scores[b].compareTo(scores[a]));
    final selectedRefs = refs.take(maxRefs).toList();

    final orb = cv.ORB.create(nFeatures: 5000);
    final bf = cv.BFMatcher.create(type: cv.NORM_HAMMING, crossCheck: true);

    final cv.Mat qColor = cv.imdecode(visionBytes, cv.IMREAD_COLOR);
    if (qColor.isEmpty) {
      return {"passed": false, "strong": false, "inliers": 0, "ratio": 0.0};
    }

    final qGray = cv.cvtColor(qColor, cv.COLOR_BGR2GRAY);
    qColor.release();

    final qKp = cv.VecKeyPoint();
    final qDesc = cv.Mat.empty();
    orb.detectAndCompute(
      qGray,
      cv.Mat.empty(),
      keypoints: qKp,
      descriptors: qDesc,
    );

    if (qDesc.isEmpty) {
      qGray.release();
      qKp.clear();
      qDesc.release();
      return {"passed": false, "strong": false, "inliers": 0, "ratio": 0.0};
    }

    final qKey = qKp.toList();

    int bestInliers = 0;
    double bestRatio = 0.0;

    for (final i in selectedRefs) {
      final dbKps = _kpCoords[i];
      final rows = _descRows[i];
      final bytes = _descBytes[i];
      if (rows < 8 || bytes.isEmpty || dbKps.isEmpty) continue;

      final dMat = cv.Mat.fromList(
        rows,
        32,
        cv.MatType(cv.MatType.CV_8U),
        bytes,
      );

      final matches = bf.match(qDesc, dMat);
      final ms = matches.toList();

      dMat.release();
      matches.clear();

      if (ms.length < inliersThreshold) continue;

      ms.sort((a, b) => a.distance.compareTo(b.distance));
      final topMatches =
          ms
              .take(topMatchesForRansac)
              .where(
                (m) =>
                    m.queryIdx >= 0 &&
                    m.queryIdx < qKey.length &&
                    m.trainIdx >= 0 &&
                    m.trainIdx < dbKps.length,
              )
              .toList();

      final src = <cv.Point2f>[];
      final dst = <cv.Point2f>[];
      for (final m in topMatches) {
        final qp = qKey[m.queryIdx];
        final p = dbKps[m.trainIdx];
        src.add(cv.Point2f(qp.x, qp.y));
        dst.add(cv.Point2f(p[0], p[1]));
      }

      if (src.length >= inliersThreshold) {
        final srcVec = cv.VecPoint2f.fromList(src);
        final dstVec = cv.VecPoint2f.fromList(dst);
        final srcMat = cv.Mat.fromVec(srcVec);
        final dstMat = cv.Mat.fromVec(dstVec);
        final mask = cv.Mat.empty();

        final H = cv.findHomography(
          srcMat,
          dstMat,
          method: cv.RANSAC,
          ransacReprojThreshold: 5.0,
          mask: mask,
        );

        if (!H.isEmpty) {
          final inliers = cv.countNonZero(mask);
          final ratio =
              topMatches.isNotEmpty ? inliers / topMatches.length : 0.0;

          if (inliers > bestInliers ||
              (inliers == bestInliers && ratio > bestRatio)) {
            bestInliers = inliers;
            bestRatio = ratio;
          }
        }

        srcMat.release();
        dstMat.release();
        mask.release();
        H.release();
      }
    }

    qGray.release();
    qKp.clear();
    qDesc.release();

    final passed =
        (bestInliers >= 8 && bestRatio >= 0.08) || (bestInliers >= 15);
    final strong =
        bestInliers >= _geometryStrongInliers &&
        bestRatio >= _geometryStrongRatio;

    return {
      "passed": passed,
      "strong": strong,
      "inliers": bestInliers,
      "ratio": bestRatio,
    };
  }

  Future<int> matchFromImageBytes(
    Uint8List imageBytes, {
    int sensorOrientation = 0,
    bool useGeometry = false,
    double? queryLat,
    double? queryLon,
    double? queryAccuracyM,
  }) async {
    if (_embedder == null || !_jsonIndexLoaded) {
      throw Exception(
        "OFFLINE ERROR: Embedder non inizializzato o indice JSON non caricato",
      );
    }

    try {
      img.Image? queryImg = img.decodeImage(imageBytes);
      if (queryImg == null) return -1;

      if (sensorOrientation != 0) {
        queryImg = img.copyRotate(
          queryImg,
          angle: sensorOrientation.toDouble(),
        );
      }

      final Uint8List visionBytes = Uint8List.fromList(
        img.encodeJpg(queryImg, quality: 95),
      );

      final queryViews = _buildQueryViews(queryImg);
      final queryViewWeights = _queryViewWeights();

      final queryEmbeddings = <List<double>>[];
      for (final view in queryViews) {
        final emb = _extractEmbedding(view);
        if (emb.isNotEmpty) {
          queryEmbeddings.add(emb);
        }
      }
      if (queryEmbeddings.isEmpty) return -1;

      final bestBySourceAll = <String, Map<String, dynamic>>{};
      final bestBySourceOrig = <String, Map<String, dynamic>>{};

      for (int i = 0; i < _dbEmbeddings.length; i++) {
        final wpId = _imgWpIds[i];
        if (wpId == -1) continue;

        final sourcePath = _sourceImagePaths[i];
        final variantName = _variantNames[i];
        final variantWeight = _variantWeights[i];

        final key = '$wpId||$sourcePath';
        final itemEmb = _dbEmbeddings[i];

        double bestScore = -1.0;
        final perViewScores = <double>[];

        for (int v = 0; v < queryEmbeddings.length; v++) {
          final rawScore = _cosine(queryEmbeddings[v], itemEmb);
          final weightedScore = rawScore * variantWeight * queryViewWeights[v];
          perViewScores.add(weightedScore);
          if (weightedScore > bestScore) {
            bestScore = weightedScore;
          }
        }

        final current = bestBySourceAll[key];
        if (current == null) {
          bestBySourceAll[key] = {
            "wpId": wpId,
            "bestScore": bestScore,
            "imgIndex": i,
            "perViewScores": perViewScores,
          };
        } else {
          final currentPerView = current["perViewScores"] as List<double>;
          for (int v = 0; v < perViewScores.length; v++) {
            currentPerView[v] = math.max(currentPerView[v], perViewScores[v]);
          }
          if (bestScore > (current["bestScore"] as double)) {
            current["bestScore"] = bestScore;
            current["imgIndex"] = i;
          }
        }

        if (variantName == "original") {
          final currentOrig = bestBySourceOrig[key];
          if (currentOrig == null) {
            bestBySourceOrig[key] = {
              "wpId": wpId,
              "bestScore": bestScore,
              "imgIndex": i,
              "perViewScores": perViewScores,
            };
          } else {
            final currentPerView = currentOrig["perViewScores"] as List<double>;
            for (int v = 0; v < perViewScores.length; v++) {
              currentPerView[v] = math.max(currentPerView[v], perViewScores[v]);
            }
            if (bestScore > (currentOrig["bestScore"] as double)) {
              currentOrig["bestScore"] = bestScore;
              currentOrig["imgIndex"] = i;
            }
          }
        }
      }

      List<Map<String, dynamic>> aggregate(
        Map<String, Map<String, dynamic>> bestBySource,
      ) {
        final byWaypoint = <int, List<Map<String, dynamic>>>{};

        for (final entry in bestBySource.values) {
          final wpId = entry["wpId"] as int;
          byWaypoint.putIfAbsent(wpId, () => []).add(entry);
        }

        final viewWinners = <int, int?>{};
        final perWaypointStats = <int, Map<String, dynamic>>{};

        byWaypoint.forEach((wpId, states) {
          states.sort(
            (a, b) =>
                (b["bestScore"] as double).compareTo(a["bestScore"] as double),
          );
          final topStates = states.take(_topItemsForWaypointScore).toList();

          final maxScore = topStates.first["bestScore"] as double;
          final meanScore =
              topStates
                  .map((s) => s["bestScore"] as double)
                  .reduce((a, b) => a + b) /
              topStates.length;

          final perViewBest = List<double>.filled(queryEmbeddings.length, -1.0);
          for (final s in topStates) {
            final scores = s["perViewScores"] as List<double>;
            for (int v = 0; v < scores.length; v++) {
              perViewBest[v] = math.max(perViewBest[v], scores[v]);
            }
          }

          perWaypointStats[wpId] = {
            "wpId": wpId,
            "maxScore": maxScore,
            "meanScore": meanScore,
            "perViewBest": perViewBest,
            "imgIndexes": topStates.map((s) => s["imgIndex"] as int).toList(),
          };
        });

        for (int v = 0; v < queryEmbeddings.length; v++) {
          int? bestWp;
          double bestScore = -1.0;
          perWaypointStats.forEach((wpId, stats) {
            final score = (stats["perViewBest"] as List<double>)[v];
            if (score > bestScore) {
              bestScore = score;
              bestWp = wpId;
            }
          });
          viewWinners[v] = bestWp;
        }

        final totalViewWeight = queryViewWeights.fold<double>(
          0.0,
          (a, b) => a + b,
        );

        final ranked = <Map<String, dynamic>>[];

        perWaypointStats.forEach((wpId, stats) {
          int voteCount = 0;
          double voteWeight = 0.0;
          for (int v = 0; v < queryEmbeddings.length; v++) {
            if (viewWinners[v] == wpId) {
              voteCount += 1;
              voteWeight += queryViewWeights[v];
            }
          }

          final voteRatio =
              totalViewWeight > 0 ? voteWeight / totalViewWeight : 0.0;

          final consensus =
              0.55 * (stats["maxScore"] as double) +
              0.25 * (stats["meanScore"] as double) +
              0.20 * voteRatio;

          ranked.add({
            "wpId": wpId,
            "consensus": consensus,
            "maxScore": stats["maxScore"],
            "meanScore": stats["meanScore"],
            "voteCount": voteCount,
            "voteRatio": voteRatio,
            "imgIndexes": stats["imgIndexes"],
          });
        });

        ranked.sort(
          (a, b) =>
              (b["consensus"] as double).compareTo(a["consensus"] as double),
        );
        return ranked;
      }

      final rankedAll = aggregate(bestBySourceAll);
      final rankedOrig = aggregate(bestBySourceOrig);

      final rankedOrigByWp = <int, Map<String, dynamic>>{
        for (final item in rankedOrig) item["wpId"] as int: item,
      };

      final candidates = <Map<String, dynamic>>[];

      for (final item in rankedAll) {
        final wpId = item["wpId"] as int;
        final orig = rankedOrigByWp[wpId];

        final allConsensus = item["consensus"] as double;
        final origConsensus = (orig?["consensus"] as double?) ?? allConsensus;

        final finalScore = 0.70 * origConsensus + 0.30 * allConsensus;

        candidates.add({
          "wpId": wpId,
          "finalScore": finalScore,
          "allConsensus": allConsensus,
          "origConsensus": origConsensus,
          "voteCount": item["voteCount"],
          "voteRatio": item["voteRatio"],
          "origVoteRatio": (orig?["voteRatio"] as double?) ?? item["voteRatio"],
          "imgIndexes": item["imgIndexes"],
        });
      }

      // GPS prior
      if (queryLat != null && queryLon != null) {
        final queryAcc = queryAccuracyM ?? _gpsDefaultAccuracyM;

        for (final c in candidates) {
          final wpId = c["wpId"] as int;
          final refs =
              (_wpToImageIndexes[wpId] ?? const <int>[])
                  .where((i) => _gpsLat[i] != null && _gpsLon[i] != null)
                  .toList();

          if (refs.isEmpty) continue;

          final idx = refs.first;
          final lat = _gpsLat[idx]!;
          final lon = _gpsLon[idx]!;
          final radius = _gpsRadiusM[idx] ?? _gpsDefaultRadiusM;

          final dist = _haversineDistanceM(queryLat, queryLon, lat, lon);
          final effectiveRadius = math.max(
            radius,
            math.max(queryAcc, _gpsDefaultRadiusM),
          );
          final farDistance = math.max(
            effectiveRadius * _gpsFarMultiplier,
            _gpsMinFarDistanceM,
          );

          double affinity;
          if (dist <= effectiveRadius) {
            affinity = 1.0;
          } else if (dist >= farDistance) {
            affinity = 0.0;
          } else {
            affinity =
                1.0 -
                ((dist - effectiveRadius) /
                    math.max(farDistance - effectiveRadius, 1.0));
          }

          final confidence = _gpsConfidenceFromAccuracy(queryAcc);
          final gpsAdjustment =
              _gpsPriorWeight * confidence * ((affinity - 0.5) * 2.0);

          c["finalScore"] = (c["finalScore"] as double) + gpsAdjustment;
        }

        candidates.sort(
          (a, b) =>
              (b["finalScore"] as double).compareTo(a["finalScore"] as double),
        );
      } else {
        candidates.sort(
          (a, b) =>
              (b["finalScore"] as double).compareTo(a["finalScore"] as double),
        );
      }

      if (candidates.isEmpty) return -1;

      final top1 = candidates[0];
      final top2 = candidates.length > 1 ? candidates[1] : null;

      final top1Final = top1["finalScore"] as double;
      final top1Orig = top1["origConsensus"] as double;
      final top2Final = top2 != null ? top2["finalScore"] as double : 0.0;
      final top2Orig = top2 != null ? top2["origConsensus"] as double : 0.0;

      final finalMargin = top1Final - top2Final;
      final origMargin = top1Orig - top2Orig;
      final voteRatio = top1["voteRatio"] as double;
      final origVoteRatio = top1["origVoteRatio"] as double;

      if (top1Final < _similarityThreshold) {
        if (useGeometry) {
          final geo = _verifyWaypointGeometry(
            top1["wpId"] as int,
            List<double>.filled(_dbEmbeddings.length, 0.0),
            visionBytes,
          );
          if (geo["strong"] == true) {
            return top1["wpId"] as int;
          }
        }
        return -1;
      }

      final directCondition =
          top1Final >= _directAcceptThreshold &&
          finalMargin >= _directAcceptMargin &&
          voteRatio >= _directAcceptMinVoteRatio &&
          top1Orig >= _originalMinForDirect;

      final softCondition =
          top1Final >= _softAcceptThreshold &&
          finalMargin >= _softAcceptMargin &&
          voteRatio >= _softAcceptMinVoteRatio &&
          top1Orig >= _originalMinForSoft;

      if (directCondition || softCondition) {
        return top1["wpId"] as int;
      }

      if (useGeometry) {
        final geoTop1 = _verifyWaypointGeometry(
          top1["wpId"] as int,
          List<double>.filled(_dbEmbeddings.length, 0.0),
          visionBytes,
        );

        Map<String, dynamic>? geoTop2;
        if (top2 != null &&
            (finalMargin < _ambiguousMargin || origMargin < _ambiguousMargin)) {
          geoTop2 = _verifyWaypointGeometry(
            top2["wpId"] as int,
            List<double>.filled(_dbEmbeddings.length, 0.0),
            visionBytes,
          );
        }

        final geometryRescueCondition =
            top1Final >= _geometryRescueMinScore &&
            finalMargin >= _geometryRescueMinMargin &&
            geoTop1["strong"] == true &&
            !(geoTop2?["strong"] == true);

        if (geometryRescueCondition) {
          return top1["wpId"] as int;
        }
      }

      return -1;
    } catch (e) {
      debugPrint('OFFLINE ERROR: Exception during matching - $e');
      return -1;
    }
  }

  void dispose() {
    _embedder?.close();
    _embedder = null;
  }
}
