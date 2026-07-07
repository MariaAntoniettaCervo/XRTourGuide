import 'dart:io';
import 'dart:typed_data';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:dio/dio.dart';
import 'package:archive/archive.dart';
import 'package:xr_tour_guide/services/auth_service.dart';
import '../services/api_service.dart';

// Cache Singleton per evitare decompressione ripetuta e saturazione RAM
class ZlibImageCache {
  static final ZlibImageCache _instance = ZlibImageCache._internal();
  factory ZlibImageCache() => _instance;
  ZlibImageCache._internal();

  // Limite cache a 50MB
  final int _maxSizeBytes = 50 * 1024 * 1024;
  int _currentSizeBytes = 0;
  final Map<String, Uint8List> _cache = {};
  final List<String> _lruKeys = [];

  Uint8List? get(String key) {
    if (_cache.containsKey(key)) {
      // Aggiorna LRU (sposta in fondo)
      _lruKeys.remove(key);
      _lruKeys.add(key);
      return _cache[key];
    }
    return null;
  }

  void put(String key, Uint8List data) {
    if (_cache.containsKey(key)) {
      _currentSizeBytes -= _cache[key]!.lengthInBytes;
      _lruKeys.remove(key);
      _cache.remove(key);
    }

    // Se l'immagine è più grande dell'intera cache, non cacharla
    if (data.lengthInBytes > _maxSizeBytes) return;

    _cache[key] = data;
    _lruKeys.add(key);
    _currentSizeBytes += data.lengthInBytes;

    _evict();
  }

  void _evict() {
    while (_currentSizeBytes > _maxSizeBytes && _lruKeys.isNotEmpty) {
      final keyToRemove = _lruKeys.removeAt(0);
      final data = _cache.remove(keyToRemove);
      if (data != null) {
        _currentSizeBytes -= data.lengthInBytes;
      }
    }
  }

  void clear() {
    _cache.clear();
    _lruKeys.clear();
    _currentSizeBytes = 0;
  }
}

// Funzione top-level per l'Isolate
List<int> _decompressIsolate(List<int> rawBytes) {
  if (rawBytes.isEmpty) return [];

  bool isValidImageHeader(List<int> bytes) {
    if (bytes.length < 4) return false;
    // PNG
    if (bytes[0] == 0x89 &&
        bytes[1] == 0x50 &&
        bytes[2] == 0x4E &&
        bytes[3] == 0x47)
      return true;
    // JPG
    if (bytes[0] == 0xFF && bytes[1] == 0xD8 && bytes[2] == 0xFF) return true;
    // GIF
    if (bytes[0] == 0x47 &&
        bytes[1] == 0x49 &&
        bytes[2] == 0x46 &&
        bytes[3] == 0x38)
      return true;
    // BMP
    if (bytes[0] == 0x42 && bytes[1] == 0x4D) return true;
    // WebP
    if (bytes.length > 12 &&
        bytes[0] == 0x52 &&
        bytes[1] == 0x49 &&
        bytes[2] == 0x46 &&
        bytes[3] == 0x46 &&
        bytes[8] == 0x57 &&
        bytes[9] == 0x45 &&
        bytes[10] == 0x42 &&
        bytes[11] == 0x50)
      return true;
    return false;
  }

  List<int> imageBytes;
  try {
    imageBytes = ZLibDecoder().decodeBytes(rawBytes);
  } catch (e) {
    try {
      imageBytes = GZipDecoder().decodeBytes(rawBytes);
    } catch (e2) {
      imageBytes = rawBytes;
    }
  }

  if (!isValidImageHeader(imageBytes)) {
    if (isValidImageHeader(rawBytes)) {
      return rawBytes;
    } else {
      throw Exception(
        "Dati non riconosciuti come immagine valida (Header sconosciuto)",
      );
    }
  }
  return imageBytes;
}

class ZlibImage extends ConsumerStatefulWidget {
  final String? url;
  final String? filePath;
  final double? width;
  final double? height;
  final BoxFit? fit;
  final Widget Function(BuildContext, Object, StackTrace?)? errorBuilder;
  final bool
  useCache; // Se true, usa la cache globale. Se false, solo memoria locale del widget.

  const ZlibImage({
    Key? key,
    this.url,
    this.filePath,
    this.width,
    this.height,
    this.fit,
    this.errorBuilder,
    this.useCache = true,
  }) : assert(url != null || filePath != null, 'Devi fornire url o filePath'),
       super(key: key);

  @override
  ConsumerState<ZlibImage> createState() => _ZlibImageState();
}

class _ZlibImageState extends ConsumerState<ZlibImage>
    with AutomaticKeepAliveClientMixin {
  Uint8List? _imageData;
  bool _loading = true;
  Object? _error;
  String? _currentKey;

  @override
  bool get wantKeepAlive => true; // Mantiene vivo il widget nelle liste

  @override
  void initState() {
    super.initState();
    _loadImage();
  }

  @override
  void didUpdateWidget(ZlibImage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.url != widget.url || oldWidget.filePath != widget.filePath) {
      _loadImage();
    }
  }

  Future<void> _loadImage() async {
    final key = widget.filePath ?? widget.url;
    if (key == null) return;

    _currentKey = key;

    // 1. Controllo Cache Globale (se abilitata)
    if (widget.useCache) {
      final cachedBytes = ZlibImageCache().get(key);
      if (cachedBytes != null) {
        if (mounted && _currentKey == key) {
          setState(() {
            _imageData = cachedBytes;
            _loading = false;
            _error = null;
          });
        }
        return;
      }
    }

    if (mounted) {
      setState(() {
        _loading = true;
        _error = null;
      });
    }

    try {
      List<int> rawBytes;

      if (widget.filePath != null) {
        // Logica Offline
        final file = File(widget.filePath!);
        if (await file.exists()) {
          rawBytes = await file.readAsBytes();
        } else {
          throw Exception("File locale non trovato: ${widget.filePath}");
        }
      } else {
        // Logica Online
        final dio = ref.read(apiServiceProvider).dio;
        final response = await dio.get<List<int>>(
          widget.url!,
          options: Options(responseType: ResponseType.bytes),
        );
        rawBytes = response.data ?? [];
      }

      if (_currentKey != key) return; // Widget aggiornato nel frattempo

      if (rawBytes.isNotEmpty) {
        // 2. Decompressione in Isolate (background)
        final imageBytes = await compute(_decompressIsolate, rawBytes);

        final uInt8List = Uint8List.fromList(imageBytes);

        // 3. Salva in Cache Globale (se abilitata)
        if (widget.useCache) {
          ZlibImageCache().put(key, uInt8List);
        }

        if (mounted && _currentKey == key) {
          setState(() {
            _imageData = uInt8List;
            _loading = false;
          });
        }
      } else {
        throw Exception("Dati immagine vuoti");
      }
    } catch (e) {
      debugPrint("Errore caricamento immagine Zlib: $e");
      if (mounted && _currentKey == key) {
        setState(() {
          _error = e;
          _loading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context); // Necessario per AutomaticKeepAliveClientMixin

    if (_loading) {
      return SizedBox(
        width: widget.width,
        height: widget.height,
        child: const Center(child: CircularProgressIndicator()),
      );
    }
    if (_error != null || _imageData == null) {
      if (widget.errorBuilder != null) {
        return widget.errorBuilder!(
          context,
          _error ?? Exception("Load failed"),
          StackTrace.current,
        );
      }
      return Container(
        width: widget.width,
        height: widget.height,
        color: Colors.grey.shade200,
        child: const Icon(Icons.broken_image, color: Colors.grey),
      );
    }
    return Image.memory(
      _imageData!,
      width: widget.width,
      height: widget.height,
      fit: widget.fit,
      errorBuilder: widget.errorBuilder,
      gaplessPlayback: true,
    );
  }
}
