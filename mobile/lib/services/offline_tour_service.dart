import 'dart:convert';
import 'dart:io';

import 'package:archive/archive.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:xr_tour_guide/services/auth_service.dart';

import 'api_service.dart';

final offlineStorageServiceProvider = Provider<OfflineStorageService>((ref) {
  final apiService = ref.read(apiServiceProvider);
  return OfflineStorageService(apiService);
});

class OfflineStorageService {
  final ApiService apiService;
  final Dio _dio = Dio();

  OfflineStorageService(this.apiService);

  static const String _offlineToursKey = 'offline_tours';
  static const String _tourDataFolder = 'offline_tours_data';

  // Get offline tours directory
  Future<Directory> get _offlineDirectory async {
    final appDir = await getApplicationDocumentsDirectory();
    final offlineDir = Directory('${appDir.path}/$_tourDataFolder');
    if (!await offlineDir.exists()) {
      await offlineDir.create(recursive: true);
    }
    return offlineDir;
  }

  // Download and store a tour offline
// Download and store a tour offline (bundle-first)
  Future<bool> downloadTourOffline(int tourId) async {
    try {
      final offlineDir = await _offlineDirectory;
      final tourDir = Directory('${offlineDir.path}/tour_$tourId');

      // pulizia preventiva per evitare mix di versioni vecchie/nuove
      if (await tourDir.exists()) {
        await tourDir.delete(recursive: true);
      }
      await tourDir.create(recursive: true);

      final bundleZip = File('${tourDir.path}/offline_bundle.zip');

      try {
        await _downloadOfflineBundle(tourId, bundleZip.path);
        await _extractZip(bundleZip, tourDir);

        // il bundle deve contenere obbligatoriamente tour_data.json
        final tourDataFile = File('${tourDir.path}/tour_data.json');
        if (!await tourDataFile.exists()) {
          throw Exception('Invalid bundle: tour_data.json missing');
        }

        await _normalizeOfflinePathsInTourData(tourDataFile, tourDir.path);

        final tourData =
            jsonDecode(await tourDataFile.readAsString())
                as Map<String, dynamic>;

        final tourJson =
            (tourData['tour'] as Map?)?.cast<String, dynamic>() ?? {};
        await _updateOfflineToursListFromPayload(tourId, tourJson);

        if (await bundleZip.exists()) {
          await bundleZip.delete();
        }

        return true;
      } on DioException catch (e) {
        // fallback opzionale: se bundle non pronto/non trovato, usa pipeline legacy
        final code = e.response?.statusCode;
        if (code == 404) {
          debugPrint(
            'Offline bundle not ready for tour $tourId',
          );
        }
        rethrow;
      }
    } catch (e) {
      debugPrint('Error downloading tour offline: $e');
      await removeTourOffline(tourId);
      return false;
    }
  }

  Future<void> _downloadOfflineBundle(int tourId, String savePath) async {
    final url = _toAbsoluteUrl('/download_offline_bundle/$tourId/');

    final response = await apiService.dio.download(
      url,
      savePath,
      options: Options(
        responseType: ResponseType.bytes,
        // headers auth già gestiti da apiService.dio interceptor/options
      ),
    );

    if (response.statusCode != 200) {
      throw Exception(
        'Failed to download offline bundle: HTTP ${response.statusCode}',
      );
    }
  }

  Future<void> _extractZip(File zipFile, Directory destinationDir) async {
    final bytes = await zipFile.readAsBytes();
    final archive = ZipDecoder().decodeBytes(bytes, verify: true);

    for (final file in archive) {
      final outPath = p.normalize(p.join(destinationDir.path, file.name));

      // protezione path traversal
      if (!outPath.startsWith(p.normalize(destinationDir.path))) {
        throw Exception('Invalid zip entry path: ${file.name}');
      }

      if (file.isFile) {
        final outFile = File(outPath);
        await outFile.parent.create(recursive: true);
        await outFile.writeAsBytes(file.content as List<int>, flush: true);
      } else {
        await Directory(outPath).create(recursive: true);
      }
    }
  }

  Future<void> _normalizeOfflinePathsInTourData(
    File tourDataFile,
    String tourRootPath,
  ) async {
    final raw = await tourDataFile.readAsString();
    final data = jsonDecode(raw) as Map<String, dynamic>;

    void normalizeWaypoint(Map<String, dynamic> wp) {
      // local_images
      final localImages = (wp['local_images'] as List?)?.cast<dynamic>() ?? [];
      wp['local_images'] =
          localImages.map((img) {
            final s = img.toString();
            if (p.isAbsolute(s)) return s;
            return p.normalize(p.join(tourRootPath, s));
          }).toList();

      // local_resources
      final localResources =
          (wp['local_resources'] as Map?)?.cast<String, dynamic>() ?? {};
      final normalizedResources = <String, dynamic>{};

      localResources.forEach((key, value) {
        if (value == null) {
          normalizedResources[key] = null;
        } else {
          final s = value.toString();
          normalizedResources[key] =
              p.isAbsolute(s) ? s : p.normalize(p.join(tourRootPath, s));
        }
      });

      // garantisci chiavi attese
      for (final k in const ['readme', 'links', 'audio', 'video', 'pdf']) {
        normalizedResources.putIfAbsent(k, () => null);
      }

      wp['local_resources'] = normalizedResources;
    }

    final waypoints = (data['waypoints'] as List?)?.cast<dynamic>() ?? [];
    for (final w in waypoints) {
      if (w is Map<String, dynamic>) {
        normalizeWaypoint(w);
      } else if (w is Map) {
        normalizeWaypoint(w.cast<String, dynamic>());
      }
    }

    final subTours = (data['sub_tours'] as List?)?.cast<dynamic>() ?? [];
    for (final st in subTours) {
      final stMap =
          (st is Map<String, dynamic>)
              ? st
              : (st as Map).cast<String, dynamic>();
      final subWps = (stMap['waypoints'] as List?)?.cast<dynamic>() ?? [];
      for (final w in subWps) {
        if (w is Map<String, dynamic>) {
          normalizeWaypoint(w);
        } else if (w is Map) {
          normalizeWaypoint(w.cast<String, dynamic>());
        }
      }
    }

    await tourDataFile.writeAsString(jsonEncode(data), flush: true);
  }


  List<String> extractMarkdownLinks(String text) {
    final regex = RegExp(
      r'''!?\[[^\]]*\]\(\s*([^\s)]+)(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)''',
      multiLine: true,
    );
    final matches = regex.allMatches(text);
    return matches.map((m) {
      final rawUrl = m.group(1)!.trim();
      final abs = _toAbsoluteUrl(rawUrl);
      return _addAttachmentParam(abs);
    }).toList();
  }

  // Converte URL relativo in assoluto usando ApiService.basicUrl
  String _toAbsoluteUrl(String url) {
    if (url.startsWith('http://') || url.startsWith('https://')) return url;
    final base = apiService.getCurrentBaseUrl(); // es: https://example.com
    if (url.startsWith('/')) return '$base$url';
    return '$base/$url';
  }
  String _addAttachmentParam(String url) {
    // Avoid adding if there's already an attachment param
    if (RegExp(r'(^|[\?&])attachment=').hasMatch(url)) return url;

    final hashIndex = url.indexOf('#');
    final fragment = (hashIndex >= 0) ? url.substring(hashIndex) : '';
    final main = (hashIndex >= 0) ? url.substring(0, hashIndex) : url;

    final qIndex = main.indexOf('?');
    if (qIndex == -1) {
      // no query: append
      return '$main?attachment=True$fragment';
    } else {
      // has query: insert right after first '?'
      return main.replaceFirst('?', '?attachment=True&') + fragment;
    }
  }

  // Update the list of offline tours
  Future<void> _updateOfflineToursListFromPayload(
    int tourId,
    Map<String, dynamic> tourJson,
  ) async {
    final prefs = await SharedPreferences.getInstance();
    final offlineToursJson = prefs.getStringList(_offlineToursKey) ?? [];

    final offlineTour = {
      'id': tourId,
      'title': (tourJson['title'] ?? '').toString(),
      'description': (tourJson['description'] ?? '').toString(),
      'downloaded_at': DateTime.now().toIso8601String(),
    };

    offlineToursJson.removeWhere((tourRaw) {
      final t = jsonDecode(tourRaw) as Map<String, dynamic>;
      return t['id'] == tourId;
    });

    offlineToursJson.add(jsonEncode(offlineTour));
    await prefs.setStringList(_offlineToursKey, offlineToursJson);
  }

  // Get list of offline tours
  Future<List<Map<String, dynamic>>> getOfflineTours() async {
    final prefs = await SharedPreferences.getInstance();
    final offlineToursJson = prefs.getStringList(_offlineToursKey) ?? [];

    return offlineToursJson
        .map((tourJson) => jsonDecode(tourJson) as Map<String, dynamic>)
        .toList();
  }

  // Check if a tour is available offline
  Future<bool> isTourAvailableOffline(int tourId) async {
    final offlineTours = await getOfflineTours();
    return offlineTours.any((tour) => tour['id'] == tourId);
  }

  // Get offline tour data
  Future<Map<String, dynamic>?> getOfflineTourData(int tourId) async {
    try {
      final offlineDir = await _offlineDirectory;
      final tourDataFile = File(
        '${offlineDir.path}/tour_$tourId/tour_data.json',
      );

      if (await tourDataFile.exists()) {
        final jsonString = await tourDataFile.readAsString();
        return jsonDecode(jsonString);
      }
      return null;
    } catch (e) {
      debugPrint('Error reading offline tour data: $e');
      return null;
    }
  }

  // Remove a tour from offline storage
  Future<bool> removeTourOffline(int tourId) async {
    try {
      // Remove tour directory
      final offlineDir = await _offlineDirectory;
      final tourDir = Directory('${offlineDir.path}/tour_$tourId');
      if (await tourDir.exists()) {
        await tourDir.delete(recursive: true);
      }

      // Update offline tours list
      final prefs = await SharedPreferences.getInstance();
      final offlineToursJson = prefs.getStringList(_offlineToursKey) ?? [];
      offlineToursJson.removeWhere((tourJson) {
        final tourData = jsonDecode(tourJson);
        return tourData['id'] == tourId;
      });
      await prefs.setStringList(_offlineToursKey, offlineToursJson);

      return true;
    } catch (e) {
      debugPrint('Error removing offline tour: $e');
      return false;
    }
  }

  // Get offline storage size
  Future<int> getOfflineStorageSize() async {
    try {
      final offlineDir = await _offlineDirectory;
      if (!await offlineDir.exists()) return 0;

      int totalSize = 0;
      await for (FileSystemEntity entity in offlineDir.list(recursive: true)) {
        if (entity is File) {
          totalSize += await entity.length();
        }
      }
      return totalSize;
    } catch (e) {
      debugPrint('Error calculating storage size: $e');
      return 0;
    }
  }

  // Clear all offline data
  Future<bool> clearAllOfflineData() async {
    try {
      final offlineDir = await _offlineDirectory;
      if (await offlineDir.exists()) {
        await offlineDir.delete(recursive: true);
      }

      final prefs = await SharedPreferences.getInstance();
      await prefs.remove(_offlineToursKey);

      return true;
    } catch (e) {
      debugPrint('Error clearing offline data: $e');
      return false;
    }
  }
}
