import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:archive/archive.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:markdown_widget/markdown_widget.dart';
import 'package:path_provider/path_provider.dart';
import 'package:xr_tour_guide/services/auth_service.dart';

import 'elements/audio_player.dart';
import 'elements/pdf_viewer.dart';
import 'elements/video_player.dart';
import 'elements/zlib_image.dart';
import 'models/app_colors.dart';
import 'services/api_service.dart';
import 'services/offline_tour_service.dart';
import 'services/tour_service.dart';
import 'utils/responsive.dart';

class ConsultationScreen extends ConsumerStatefulWidget {
  final int tourId;
  final int waypointId;
  final bool isOffline;
  final String landmarkName;
  final String landmarkDescription;
  final List<String> landmarkImages;

  const ConsultationScreen({
    Key? key,
    required this.tourId,
    required this.waypointId,
    required this.isOffline,
    this.landmarkName = "",
    this.landmarkDescription = "",
    this.landmarkImages = const [],
  }) : super(key: key);

  @override
  ConsumerState<ConsultationScreen> createState() => _ConsultationScreenState();
}

class _ConsultationScreenState extends ConsumerState<ConsultationScreen> {
  late final TourService _tourService;
  late final ApiService _apiService;
  late final OfflineStorageService _offlineService;

  final DraggableScrollableController _sheetController =
      DraggableScrollableController();

  static const double _initialSheetSize = 0.1;
  static const double _minSheetSize = 0.1;
  static const double _maxSheetSize = 0.8;

  final Map<String, dynamic> _availableResources = {
    "readme": 0,
    "links": 0,
    "images": 0,
    "video": 0,
    "pdf": 0,
    "audio": 0,
  };

  final Map<String, Map<String, dynamic>> _preloadedContent = {};
  final Map<String, File> _cachedResources = {};
  final Map<String, Map<String, dynamic>> _resourceMetaCache = {};
  final List<File> _tempFiles = [];

  Widget? _currentActiveContent;
  String _currentMarkdownContent = "";

  bool _isLoading = true;

  String _landmarkName = "";
  String _landmarkDescription = "";
  List<String> _landmarkImages = [];

  @override
  void initState() {
    super.initState();

    _tourService = ref.read(tourServiceProvider);
    _apiService = ref.read(apiServiceProvider);
    _offlineService = ref.read(offlineStorageServiceProvider);

    _landmarkName = widget.landmarkName;
    _landmarkDescription = widget.landmarkDescription;
    _landmarkImages = widget.landmarkImages;

    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadAndPreloadResources();
    });
  }

  @override
  void dispose() {
    _sheetController.dispose();
    _clearTempFiles();
    super.dispose();
  }

  Future<Map<String, dynamic>> _getResourceWithMetaCache(
    int waypointId,
    String resourceType,
  ) async {
    final key = '$waypointId:$resourceType';
    final cached = _resourceMetaCache[key];
    if (cached != null) return cached;

    final response = await _tourService.getResourceByWaypointAndType(
      waypointId,
      resourceType,
    );
    final map = (response as Map<String, dynamic>);
    _resourceMetaCache[key] = map;
    return map;
  }

  Future<void> _loadAndPreloadResources() async {
    try {
      final available = {
        "readme": 0,
        "links": 0,
        "images": 0,
        "video": 0,
        "pdf": 0,
        "audio": 0,
      };

      if (widget.isOffline) {
        await _loadOfflineResources(available);
      } else {
        await _loadOnlineResources(available);
      }

      if (!mounted) return;

      setState(() {
        _availableResources
          ..clear()
          ..addAll(available);

        _currentMarkdownContent = "# $_landmarkName\n\n$_landmarkDescription";

        _currentActiveContent = MarkdownWidget(
          data: _currentMarkdownContent,
          config: _buildMarkdownConfig(),
          padding: const EdgeInsets.only(top: 0),
          shrinkWrap: true,
        );

        _isLoading = false;
      });

      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;

        if (_sheetController.isAttached) {
          _sheetController.animateTo(
            _initialSheetSize + 0.25,
            duration: const Duration(milliseconds: 300),
            curve: Curves.easeInOut,
          );
        }
      });
      
    } catch (e) {
      debugPrint("Error loading consultation resources: $e");

      if (!mounted) return;

      setState(() {
        _isLoading = false;
        _currentActiveContent = const Text(
          "Error loading resources.",
          style: TextStyle(color: AppColors.textPrimary),
        );
      });
    }
  }

  Future<void> _loadOfflineResources(Map<String, int> available) async {
    final offlineData = await _offlineService.getOfflineTourData(widget.tourId);
    if (offlineData == null) return;

    final List<dynamic> allWaypoints = [];

    final mainWaypoints = (offlineData["waypoints"] as List?) ?? [];
    allWaypoints.addAll(mainWaypoints);

    final subTours = (offlineData["sub_tours"] as List?) ?? [];
    for (final st in subTours) {
      if (st is Map<String, dynamic>) {
        final subWaypoints = (st["waypoints"] as List?) ?? [];
        allWaypoints.addAll(subWaypoints);
      }
    }

    Map<String, dynamic>? selectedWaypoint;

    for (final item in allWaypoints) {
      if (item is Map<String, dynamic>) {
        final id = (item["id"] as num?)?.toInt();
        if (id == widget.waypointId) {
          selectedWaypoint = item;
          break;
        }
      }
    }

    if (selectedWaypoint == null) return;

    _landmarkName =
        selectedWaypoint["title"]?.toString().trim().isNotEmpty == true
            ? selectedWaypoint["title"].toString()
            : _landmarkName;

    _landmarkDescription =
        selectedWaypoint["description"]?.toString().trim().isNotEmpty == true
            ? selectedWaypoint["description"].toString()
            : _landmarkDescription;

    final localImages =
        (selectedWaypoint["local_images"] as List?)?.cast<String>() ??
        <String>[];

    final localResources =
        (selectedWaypoint["local_resources"] as Map?)
            ?.cast<String, dynamic>() ??
        <String, dynamic>{};

    if (localImages.isNotEmpty) {
      available["images"] = 1;
      _preloadedContent["images"] = {"images": localImages};
      _landmarkImages = localImages;
    }

    for (final type in ["readme", "links", "video", "pdf", "audio"]) {
      final value = localResources[type];

      if (value is String && value.isNotEmpty) {
        available[type] = 1;
        _preloadedContent[type] = {type: value};
      } else if (value is List && value.isNotEmpty) {
        available[type] = 1;
        _preloadedContent[type] = {type: value};
      }
    }
  }

  Future<void> _loadOnlineResources(Map<String, int> available) async {
    const types = ["readme", "links", "images", "video", "pdf", "audio"];

    for (final type in types) {
      try {
        final response = await _tourService.getResourceByWaypointAndType(
          widget.waypointId,
          type,
        );

        if (response.isEmpty || response.containsKey("error")) {
          continue;
        }

        if (type == "images") {
          final images = (response["images"] as List?)?.cast<String>() ?? [];

          if (images.isNotEmpty) {
            available["images"] = 1;
            _preloadedContent["images"] = {"images": images};
            _landmarkImages = images;

            for (final imagePath in images) {
              final imageUrl = _normalizeRemoteUrl(imagePath);

              if (mounted) {
                unawaited(
                  precacheImage(CachedNetworkImageProvider(imageUrl), context),
                );
              }
            }
          }
        } else if (type == "links") {
          final links = (response["links"] as List?)?.cast<String>() ?? [];

          if (links.isNotEmpty) {
            available["links"] = 1;
            _preloadedContent["links"] = {"links": links};
          }
        } else {
          final url = response["url"]?.toString() ?? "";

          if (url.isNotEmpty) {
            available[type] = 1;
            _preloadedContent[type] = {type: url};
          }
        }
      } catch (e) {
        debugPrint("Error preloading $type: $e");
      }
    }
  }

  String _normalizeRemoteUrl(String sourcePath) {
    if (sourcePath.startsWith("http://") || sourcePath.startsWith("https://")) {
      return sourcePath;
    }

    final baseUrl = _apiService.getCurrentBaseUrl();

    if (sourcePath.startsWith("/")) {
      return "$baseUrl$sourcePath";
    }

    return "$baseUrl/$sourcePath";
  }

  List<int> _decompressBytes(List<int> rawBytes) {
    try {
      return ZLibDecoder().decodeBytes(rawBytes);
    } catch (_) {
      try {
        return GZipDecoder().decodeBytes(rawBytes);
      } catch (_) {
        return rawBytes;
      }
    }
  }

  Future<File?> _loadAndDecompressResource(
    String sourcePath,
    bool isLocal,
    String extension,
  ) async {
    if (_cachedResources.containsKey(sourcePath)) {
      final cachedFile = _cachedResources[sourcePath]!;

      if (await cachedFile.exists()) {
        return cachedFile;
      }

      _cachedResources.remove(sourcePath);
    }

    try {
      List<int> rawBytes;

      if (isLocal) {
        final file = File(sourcePath);

        if (!await file.exists()) {
          throw Exception("File not found at $sourcePath");
        }

        rawBytes = await file.readAsBytes();
      } else {
        final url = _normalizeRemoteUrl(sourcePath);

        final response = await Dio().get(
          url,
          options: Options(responseType: ResponseType.bytes),
        );

        if (response.statusCode == 200) {
          rawBytes = response.data ?? [];
        } else {
          throw Exception(
            "Failed to download resource from $sourcePath, "
            "status code: ${response.statusCode}",
          );
        }
      }

      final decompressedBytes = _decompressBytes(rawBytes);
      final tempDir = await getTemporaryDirectory();

      final tempFile = File(
        "${tempDir.path}/consultation_resource_"
        "${DateTime.now().millisecondsSinceEpoch}.$extension",
      );

      await tempFile.writeAsBytes(decompressedBytes, flush: true);

      _tempFiles.add(tempFile);
      _cachedResources[sourcePath] = tempFile;

      return tempFile;
    } catch (e) {
      debugPrint("Error loading/decompressing resource: $e");
      _showError("Error loading resource");
      return null;
    }
  }

  Future<void> _clearTempFiles() async {
    for (final file in _tempFiles) {
      try {
        if (await file.exists()) {
          await file.delete();
        }
      } catch (e) {
        debugPrint("Error deleting temp file ${file.path}: $e");
      }
    }

    _tempFiles.clear();
  }

  MarkdownConfig _buildMarkdownConfig() {
    return MarkdownConfig(
      configs: [
        PConfig(
          textStyle: TextStyle(
            fontSize: context.r.sp(16),
            height: 1.5,
            color: AppColors.textSecondary,
          ),
        ),
        H1Config(
          style: TextStyle(
            fontSize: context.r.sp(24),
            fontWeight: FontWeight.bold,
            color: AppColors.textPrimary,
          ),
        ),
        H2Config(
          style: TextStyle(
            fontSize: context.r.sp(20),
            fontWeight: FontWeight.bold,
            color: AppColors.textPrimary,
          ),
        ),
        LinkConfig(
          style: const TextStyle(
            color: AppColors.primary,
            decoration: TextDecoration.underline,
          ),
        ),
        ImgConfig(
          builder: (url, attributes) {
            if (url.startsWith("file://")) {
              String localPath;

              try {
                localPath = Uri.parse(url).toFilePath();
              } catch (_) {
                localPath = url.substring(7);
              }

              return Container(
                margin: const EdgeInsets.symmetric(vertical: 8),
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(12),
                  child: ZlibImage(
                    filePath: localPath,
                    fit: BoxFit.cover,
                    useCache: false,
                    errorBuilder: (context, error, stackTrace) {
                      return _buildImagePlaceholder(
                        width: double.infinity,
                        height: 180,
                      );
                    },
                  ),
                ),
              );
            }

            final imageUrl = _normalizeRemoteUrl(url);

            return Container(
              margin: const EdgeInsets.symmetric(vertical: 8),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(12),
                child: CachedNetworkImage(
                  imageUrl: imageUrl,
                  fit: BoxFit.cover,
                  memCacheWidth: 1200,
                  maxWidthDiskCache: 1600,
                  placeholder:
                      (context, url) => const SizedBox(
                        height: 180,
                        child: Center(
                          child: CircularProgressIndicator(strokeWidth: 2),
                        ),
                      ),
                  errorWidget: (context, url, error) {
                    return _buildImagePlaceholder(
                      width: double.infinity,
                      height: 180,
                    );
                  },
                ),
              ),
            );
          },
        ),
        BlockquoteConfig(
          sideColor: AppColors.primary.withOpacity(0.5),
          textColor: AppColors.textSecondary,
        ),
      ],
    );
  }

  Future<void> _updateDraggableSheetContent(String type, int waypointId) async {
    Widget? contentToDisplay;
    Map<String, dynamic> content = {};

    var queryType = type;

    if (type == "text") {
      queryType = "readme";
    } else if (type == "link") {
      queryType = "links";
    } else if (type == "document") {
      queryType = "pdf";
    } else if (type == "image") {
      queryType = "images";
    }

    setState(() {
      _currentActiveContent = const Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            CircularProgressIndicator(),
            SizedBox(height: 16),
            Text(
              "Loading content...",
              style: TextStyle(color: AppColors.textPrimary),
            ),
          ],
        ),
      );
    });

    _sheetController.animateTo(
      _initialSheetSize + 0.25,
      duration: const Duration(milliseconds: 300),
      curve: Curves.easeInOut,
    );

    try {
      final preloaded = _preloadedContent[queryType];

      if (preloaded != null) {
        content = preloaded;
      } else if (widget.isOffline) {
        content = {};
      } else {
        // final response = await _tourService.getResourceByWaypointAndType(
        //   waypointId,
        //   queryType,
        // );

        // content = response;
        content = await _getResourceWithMetaCache(waypointId, queryType);


        if (content.containsKey("url")) {
          content[queryType] = content["url"];
        }

        _preloadedContent[queryType] = content;
      }
    } catch (e) {
      debugPrint("Error retrieving content: $e");
      type = "error";
    }

    switch (type) {
      case "text":
        final readmePath = content["readme"]?.toString() ?? "";

        if (readmePath.isNotEmpty) {
          final textFile = await _loadAndDecompressResource(
            readmePath,
            widget.isOffline,
            "md",
          );

          if (textFile != null) {
            _currentMarkdownContent = await textFile.readAsString();
          } else {
            _currentMarkdownContent = "Error loading readme content.";
          }
        } else {
          _currentMarkdownContent =
              "# $_landmarkName\n\nNo readme available for this waypoint.";
        }

        contentToDisplay = MarkdownWidget(
          data: _currentMarkdownContent,
          config: _buildMarkdownConfig(),
          padding: const EdgeInsets.only(top: 0),
          shrinkWrap: true,
        );
        break;

      case "link":
        final linksList = await _extractLinks(content);

        if (linksList.isNotEmpty) {
          final mdBuffer = StringBuffer("# $_landmarkName Links\n\n");

          for (final link in linksList) {
            mdBuffer.writeln("- [$link]($link)\n");
          }

          _currentMarkdownContent = mdBuffer.toString();
        } else {
          _currentMarkdownContent =
              "# $_landmarkName\n\nNo links available for this waypoint.";
        }

        contentToDisplay = MarkdownWidget(
          data: _currentMarkdownContent,
          config: _buildMarkdownConfig(),
          padding: const EdgeInsets.only(top: 0),
          shrinkWrap: true,
        );
        break;

      case "image":
        final imagesList = (content["images"] as List?)?.cast<String>() ?? [];

        if (imagesList.isNotEmpty) {
          final mdBuffer = StringBuffer("# $_landmarkName\n\n");

          for (final imgPath in imagesList) {
            final markdownImageUrl =
                widget.isOffline
                    ? Uri.file(imgPath).toString()
                    : _normalizeRemoteUrl(imgPath);

            mdBuffer.writeln("![Image]($markdownImageUrl)\n\n");
          }

          _currentMarkdownContent = mdBuffer.toString();
        } else {
          _currentMarkdownContent =
              "# $_landmarkName\n\nNo images available for this waypoint.";
        }

        contentToDisplay = MarkdownWidget(
          data: _currentMarkdownContent,
          config: _buildMarkdownConfig(),
          padding: const EdgeInsets.only(top: 0),
          shrinkWrap: true,
        );
        break;

      // case "video":
      //   final videoPath = content["video"]?.toString() ?? "";

      //   if (videoPath.isNotEmpty) {
      //     final videoFile = await _loadAndDecompressResource(
      //       videoPath,
      //       widget.isOffline,
      //       "mp4",
      //     );

      //     if (videoFile != null) {
      //       contentToDisplay = VideoPlayerWidget(
      //         videoUrl: videoFile.path,
      //         isLocalFile: true,
      //       );
      //     }
      //   }

      //   contentToDisplay ??= _buildEmptyContent("No video available.");
      //   break;
      case 'video':
        final videoPath = (content['video'] ?? content['url'] ?? '').toString();
        if (videoPath.isNotEmpty) {
          if (widget.isOffline) {
            final videoFile = await _loadAndDecompressResource(
              videoPath,
              true,
              'mp4',
            );
            contentToDisplay =
                (videoFile != null)
                    ? VideoPlayerWidget(
                      videoUrl: videoFile.path,
                      isLocalFile: true,
                    )
                    : const Center(
                      child: Text("Errore nel caricamento del video"),
                    );
          } else {
            final videoUrl =
                videoPath.startsWith('http')
                    ? videoPath
                    : "${_apiService.getCurrentBaseUrl()}$videoPath";
            contentToDisplay = VideoPlayerWidget(
              videoUrl: videoUrl,
              isLocalFile: false,
            );
          }
        } else {
          contentToDisplay = const Center(
            child: Text('No video available for this waypoint.'),
          );
        }
        break;

      // case "document":
      //   final pdfPath = content["pdf"]?.toString() ?? "";

      //   if (pdfPath.isNotEmpty) {
      //     final pdfFile = await _loadAndDecompressResource(
      //       pdfPath,
      //       widget.isOffline,
      //       "pdf",
      //     );

      //     if (pdfFile != null) {
      //       contentToDisplay = PdfViewerWidget(
      //         pdfUrl: pdfFile.path,
      //         isLocalFile: true,
      //       );
      //     }
      //   }

      //   contentToDisplay ??= _buildEmptyContent("No document available.");
      //   break;

      case 'document':
        final pdfPath = (content['pdf'] ?? content['url'] ?? '').toString();
        if (pdfPath.isNotEmpty) {
          if (widget.isOffline) {
            final pdfFile = await _loadAndDecompressResource(
              pdfPath,
              true,
              'pdf',
            );
            contentToDisplay =
                (pdfFile != null)
                    ? PdfViewerWidget(pdfUrl: pdfFile.path, isLocalFile: true)
                    : const Center(
                      child: Text("Errore nel caricamento del PDF"),
                    );
          } else {
            final pdfUrl =
                pdfPath.startsWith('http')
                    ? pdfPath
                    : "${_apiService.getCurrentBaseUrl()}$pdfPath";
            contentToDisplay = PdfViewerWidget(
              pdfUrl: pdfUrl,
              isLocalFile: false,
            );
          }
        } else {
          contentToDisplay = const Center(
            child: Text('No PDF document available for this waypoint.'),
          );
        }
        break;

      case "audio":
        final audioPath = content["audio"]?.toString() ?? "";

        if (audioPath.isNotEmpty) {
          final audioFile = await _loadAndDecompressResource(
            audioPath,
            widget.isOffline,
            "mp3",
          );

          if (audioFile != null) {
            contentToDisplay = AudioPlayerWidget(
              audioUrl: audioFile.path,
              isLocalFile: true,
            );
          }
        }

        contentToDisplay ??= _buildEmptyContent("No audio available.");
        break;

      default:
        contentToDisplay = _buildEmptyContent("Error loading content.");
        break;
    }

    if (!mounted) return;

    setState(() {
      _currentActiveContent = contentToDisplay;
    });
  }

  Future<List<String>> _extractLinks(Map<String, dynamic> content) async {
    final linksData = content["links"];

    if (linksData is List) {
      return linksData.map((e) => e.toString()).toList();
    }

    if (linksData is String && linksData.isNotEmpty) {
      if (widget.isOffline) {
        try {
          final file = File(linksData);

          if (await file.exists()) {
            final fileContent = await file.readAsString();

            try {
              final decoded = jsonDecode(fileContent);

              if (decoded is List) {
                return decoded.map((e) => e.toString()).toList();
              }
            } catch (_) {
              return fileContent
                  .split("\n")
                  .where((line) => line.trim().isNotEmpty)
                  .toList();
            }
          }
        } catch (e) {
          debugPrint("Error reading links file: $e");
        }
      }

      return [linksData];
    }

    return [];
  }

  Widget _buildEmptyContent(String message) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          _landmarkName,
          style: TextStyle(
            fontSize: context.r.sp(24),
            fontWeight: FontWeight.bold,
            color: AppColors.textPrimary,
          ),
        ),
        const SizedBox(height: 12),
        Text(
          message,
          style: TextStyle(fontSize: context.r.sp(16), color: AppColors.textSecondary),
        ),
      ],
    );
  }

  Widget _buildImagePlaceholder({double width = 150, double height = 100}) {
    return Container(
      width: width,
      height: height,
      decoration: BoxDecoration(
        color: Colors.grey.shade300,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Icon(Icons.image_not_supported, color: Colors.grey.shade600),
    );
  }

  List<Map<String, dynamic>> _getAvailableIconsData() {
    return [
      {
        "type": "text",
        "label": "Text",
        "assetPath": "assets/icons/text.png",
        "angle": -pi / 2,
        "isVisible": _availableResources["readme"] == 1,
      },
      {
        "type": "link",
        "label": "Link",
        "assetPath": "assets/icons/link.png",
        "angle": -pi / 4.5,
        "isVisible": _availableResources["links"] == 1,
      },
      {
        "type": "image",
        "label": "Image",
        "assetPath": "assets/icons/image.png",
        "angle": pi / 4.5,
        "isVisible": _availableResources["images"] == 1,
      },
      {
        "type": "video",
        "label": "Video",
        "assetPath": "assets/icons/video.png",
        "angle": pi / 2,
        "isVisible": _availableResources["video"] == 1,
      },
      {
        "type": "document",
        "label": "Doc",
        "assetPath": "assets/icons/document.png",
        "angle": 2 * pi / 2.5,
        "isVisible": _availableResources["pdf"] == 1,
      },
      {
        "type": "audio",
        "label": "Audio",
        "assetPath": "assets/icons/audio.png",
        "angle": -2 * pi / 2.5,
        "isVisible": _availableResources["audio"] == 1,
      },
    ];
  }

  Widget _buildResourceCircle() {
    final screenWidth = MediaQuery.of(context).size.width;
    final screenHeight = MediaQuery.of(context).size.height;

    final centerX = screenWidth / 2;
    final centerY = screenHeight / 2;

    final responsive = context.r;


    final iconRadius = responsive.consultationIconRadius();
    final iconSize = responsive.consultationIconSize();

    final iconsData = _getAvailableIconsData();
    final visibleIcons =
        iconsData.where((item) => item["isVisible"] == true).toList();

    return Stack(
      children: [
        Center(
          child: Container(
            width: 65,
            height: 65,
            decoration: BoxDecoration(
              color: visibleIcons.isEmpty ? Colors.grey : Colors.green,
              shape: BoxShape.circle,
              boxShadow: [
                BoxShadow(
                  color: (visibleIcons.isEmpty ? Colors.grey : Colors.green)
                      .withOpacity(0.4),
                  blurRadius: 20,
                  spreadRadius: 5,
                ),
              ],
            ),
            child: Icon(
              visibleIcons.isEmpty ? Icons.info_outline : Icons.check,
              color: Colors.white,
              size: 40,
            ),
          ),
        ),
        ...iconsData.map((elementData) {
          final angle = elementData["angle"] as double;
          final x = centerX + iconRadius * cos(angle);
          final y = centerY + iconRadius * sin(angle);

          return Positioned(
            left: x - iconSize / 2,
            top: y - iconSize / 2,
            child: _buildSimpleResourceIcon(
              label: elementData["label"] as String,
              isVisible: elementData["isVisible"] == true,
              assetPath: elementData["assetPath"] as String,
              iconSize: iconSize,
              onTap: () {
                _updateDraggableSheetContent(
                  elementData["type"] as String,
                  widget.waypointId,
                );
              },
            ),
          );
        }).toList(),
      ],
    );
  }

  Widget _buildSimpleResourceIcon({
    required String label,
    required String assetPath,
    required bool isVisible,
    required VoidCallback onTap,
    double iconSize = 50,
  }) {
    if (!isVisible) {
      return const SizedBox.shrink();
    }

    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: Image.asset(
        assetPath,
        width: iconSize,
        height: iconSize,
        fit: BoxFit.contain,
        errorBuilder: (context, error, stackTrace) {
          return Icon(Icons.broken_image, size: iconSize, color: Colors.red);
        },
      ),
    );
  }

  Widget _buildBackButton(BuildContext context) {
    final screenHeight = MediaQuery.of(context).size.height;
    final screenWidth = MediaQuery.of(context).size.width;
    final buttonSize = context.r.roundButtonSize();

    return Positioned(
      top: MediaQuery.of(context).padding.top + context.r.space(25),
      left: 15,
      child: Container(
        width: buttonSize,
        height: buttonSize,
        decoration: BoxDecoration(
          color: AppColors.background.withOpacity(0.9),
          shape: BoxShape.circle,
          boxShadow: [
            BoxShadow(
              color: AppColors.cardShadow,
              blurRadius: 8,
              offset: const Offset(0, 2),
            ),
          ],
        ),
        child: IconButton(
          onPressed: () => Navigator.of(context).pop(),
          icon: const Icon(
            Icons.arrow_back,
            color: AppColors.textPrimary,
            size: 28,
          ),
          padding: EdgeInsets.zero,
        ),
      ),
    );
  }

  Widget _buildDraggableSheet(BuildContext context) {
    return DraggableScrollableSheet(
      key: const ValueKey("ConsultationDraggableSheet"),
      controller: _sheetController,
      initialChildSize: _initialSheetSize,
      minChildSize: _minSheetSize,
      maxChildSize: _maxSheetSize,
      builder: (context, scrollController) {
        return Container(
          decoration: const BoxDecoration(
            color: AppColors.background,
            borderRadius: BorderRadius.only(
              topLeft: Radius.circular(20),
              topRight: Radius.circular(20),
            ),
            boxShadow: [
              BoxShadow(
                color: AppColors.cardShadow,
                blurRadius: 10,
                offset: Offset(0, -2),
              ),
            ],
          ),
          child: Column(
            children: [
              Container(
                margin: const EdgeInsets.only(top: 12, bottom: 8),
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                  color: AppColors.divider,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
              Expanded(
                child:
                    _currentActiveContent != null
                        ? SingleChildScrollView(
                          controller: scrollController,
                          padding: const EdgeInsets.symmetric(
                            horizontal: 20,
                            vertical: 10,
                          ),
                          child: _currentActiveContent!,
                        )
                        : Center(
                          child: Text(
                            "Select content type.",
                            style: Theme.of(context).textTheme.titleLarge
                                ?.copyWith(color: AppColors.textPrimary),
                          ),
                        ),
              ),
            ],
          ),
        );
      },
    );
  }

  void _showError(String message) {
    if (!mounted) return;

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), backgroundColor: Colors.redAccent),
    );
  }

  @override
  Widget build(BuildContext context) {
    final staticOuterCircleSize = context.r.consultationOuterCircleSize();

    return Scaffold(
      backgroundColor: const Color.fromARGB(255, 148, 145, 145),
      extendBodyBehindAppBar: true,
      body: Stack(
        children: [
          Positioned.fill(
            child: Image.asset(
              'assets/sfondo_consultazione.png',
              fit: BoxFit.cover,
            ),
          ),
          Center(
            child: Container(
              width: staticOuterCircleSize,
              height: staticOuterCircleSize,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                border: Border.all(
                  color: Colors.black.withOpacity(0.2),
                  width: 4,
                ),
              ),
            ),
          ),
          if (_isLoading)
            const Center(
              child: CircularProgressIndicator(color: AppColors.primary),
            )
          else
            _buildResourceCircle(),
          _buildBackButton(context),
          _buildDraggableSheet(context),
        ],
      ),
    );
  }
}
