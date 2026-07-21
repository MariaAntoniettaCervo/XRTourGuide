import 'dart:convert';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:camera/camera.dart';
import 'models/app_colors.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:geolocator/geolocator.dart';
import 'package:flutter_map_location_marker/flutter_map_location_marker.dart';
import 'package:markdown_widget/markdown_widget.dart'; // Keep this for text/link/image
import 'dart:async';
import 'dart:math';
import 'services/auth_service.dart';
import 'services/tour_service.dart';
import 'services/api_service.dart';
import 'services/local_state_service.dart';
import 'models/waypoint.dart';
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:easy_localization/easy_localization.dart";
import 'services/offline_tour_service.dart';
import "dart:io";
import "package:path_provider/path_provider.dart";
import 'package:flutter_map_pmtiles/flutter_map_pmtiles.dart';
import 'dart:typed_data';
import 'package:image/image.dart' as img;
import 'package:permission_handler/permission_handler.dart';
import 'package:dio/dio.dart';
import 'package:archive/archive.dart';
import 'package:flutter/foundation.dart';
import 'services/analytics_service.dart';

// Import for AR
import 'package:ar_flutter_plugin_plus/ar_flutter_plugin.dart';
import 'package:ar_flutter_plugin_plus/datatypes/config_planedetection.dart';
import 'package:ar_flutter_plugin_plus/datatypes/hittest_result_types.dart';
import 'package:ar_flutter_plugin_plus/datatypes/node_types.dart';
import 'package:ar_flutter_plugin_plus/managers/ar_location_manager.dart';
import 'package:ar_flutter_plugin_plus/managers/ar_session_manager.dart';
import 'package:ar_flutter_plugin_plus/managers/ar_object_manager.dart';
import 'package:ar_flutter_plugin_plus/managers/ar_anchor_manager.dart';
import 'package:ar_flutter_plugin_plus/models/ar_anchor.dart';
import 'package:ar_flutter_plugin_plus/models/ar_node.dart';
import 'package:ar_flutter_plugin_plus/models/ar_hittest_result.dart';
import 'package:vector_math/vector_math_64.dart' as vector;
import 'package:cached_network_image/cached_network_image.dart';
import 'models/ARPlatformConfig.dart';
import 'services/offline_recognition_isolate_service.dart';


// New imports for media players/viewers
import 'elements/pdf_viewer.dart';
import 'elements/audio_player.dart';
import 'elements/video_player.dart';
import 'elements/zlib_image.dart';
import 'utils/responsive.dart';

// Enum for recognition states
enum RecognitionState {
  ready, // Initial state - show camera button
  scanning, // Currently scanning
  success, // Recognition successful
  failure, // Recognition failed,
}

Future<Uint8List> _processImageInIsolate(Map<String, dynamic> params) async {
  final Uint8List bytes = params['bytes'];
  final int orientation = params['orientation'];

  img.Image? capturedImage = img.decodeImage(bytes);
  if (capturedImage == null) {
    throw Exception("Failed to decode image");
  }

  if (orientation != 0) {
    capturedImage = img.copyRotate(capturedImage, angle: orientation);
  }

  const int targetShortestSide = 1024;
  final int shortestSide = min(capturedImage.width, capturedImage.height);

  if (shortestSide > targetShortestSide) {
    final double scale = targetShortestSide / shortestSide;
    capturedImage = img.copyResize(
      capturedImage,
      width: (capturedImage.width * scale).round(),
      height: (capturedImage.height * scale).round(),
      interpolation: img.Interpolation.linear
    );
  }

  // capturedImage = img.copyResize(capturedImage, width: 224, height: 224);

  return Uint8List.fromList(img.encodeJpg(capturedImage, quality: 85));
}


// _currentMarkdownContent is kept to build markdown strings for MarkdownWidget
String _currentMarkdownContent = "";
// This new variable will hold the actual Widget to display in the sheet
Widget? _currentActiveContent;

class ARCameraScreen extends ConsumerStatefulWidget {
  // Landmark data passed to the screen
  String landmarkName;
  String landmarkDescription;
  List<String> landmarkImages;
  final double latitude;
  final double longitude;
  final int tourId;
  final bool isOffline;
  final bool enableRecognition;
  final int? initialWaypointId;
  final String? tourType;

  ARCameraScreen({
    Key? key,
    required this.tourId,
    this.landmarkName = "",
    this.landmarkDescription = """
""",
    this.landmarkImages = const [],
    required this.latitude,
    required this.longitude,
    this.isOffline = false,
    this.enableRecognition = true,
    this.initialWaypointId,
    this.tourType,
  }) : super(key: key);

  @override
  ConsumerState<ARCameraScreen> createState() => _ARCameraScreenState();
}

class _ARCameraScreenState extends ConsumerState<ARCameraScreen>
    with TickerProviderStateMixin {

  late ApiService _apiService;
  late LocalStateService _localStateService;
  late OfflineStorageService _offlineService;
  late AnalyticsService _analytics;
  OfflineRecognitionIsolateService? _offlineRecognitionService;

  bool _isProcessingFrame = false;


  // Camera controller
  CameraController? _cameraController;
  List<CameraDescription>? _cameras;
  bool _isCameraInitialized = false;
  double _minZoomLevel = 1.0;
  double _maxZoomLevel = 1.0;
  double _currentZoomLevel = 1.0;
  double _baseZoomLevel = 1.0;

  // Recognition state
  RecognitionState _recognitionState = RecognitionState.ready;

  String _recognitionFailureMessage = "";

  final List<String> _recognitionFailureMessages = [
    "rec_failure_1".tr(),
    "rec_failure_2".tr(),
    "rec_failure_3".tr(),
    "rec_failure_4".tr(),
    "rec_failure_5".tr(),
    "rec_failure_6".tr(),
    "rec_failure_7".tr(),
    "rec_failure_8".tr(),
  ];

  int _recognizedWaypointId = -1; // Store recognized waypoint ID
  Map<String, dynamic> _availableResources = {}; // Store available resources

  // Animation controllers
  late AnimationController _pulseAnimationController;
  late AnimationController _successAnimationController;
  late AnimationController _failureAnimationController;
  late Animation<double> _pulseAnimation;
  late Animation<double> _successAnimation;
  late Animation<double> _failureAnimation;

  // Controller for the draggable sheet
  final DraggableScrollableController _sheetController =
      DraggableScrollableController();

  // Initial size of the draggable sheet (10% of screen height)
  final double _initialSheetSize = 0.1;
  final double _minSheetSize = 0.1;
  final double _maxSheetSize = 0.8;

  // Flutter Map controller for the mini-map
  final MapController _mapController = MapController();

  // Current position for location tracking
  Position? _currentPosition;

  // Manual animation progress for AR overlays
  double _arOverlayProgress = 0.0;

  late TourService _tourService;

  List<Waypoint> _waypoints = [];
  Map<int, List<String>> _offlineImagesByWaypoint = {};
  Map<int, Map<String, dynamic>> _offlineResourcesByWaypoint = {};

  bool _isLoadingWaypoints = true;

  String? _pmtilesPath;
  late Future<PmTilesTileProvider> _futureTileProvider;

  //LISTA PER MANTENERE TRACCIA DEI FILE TEMPORANEI SCARICATI E DECOMPRESSI
  final List<File> _tempFiles = [];

  final Map<String, File> _cachedResources = {};
  final Map<String, Map<String, dynamic>> _resourceMetaCache = {};

  //AR Variables
  bool _isARMode = false;
  static const double _totemStartScale = 0.5;
  static const double _totemTargetScale = 15.0;

  ARSessionManager? arSessionManager;
  ARObjectManager? arObjectManager;
  ARAnchorManager? arAnchorManager;

  ARNode? _totemBaseNode;
  ARNode? _totemBodyNode;

  ARNode? _totemMarkdownCardNode;
  Timer? _markdownScrollTimer;
  int _markdownScrollFrame = 0;
  double _markdownMaxScrollOffset = 0.0;
  bool _markdownScrollDown = true;

  bool _totemSpawned = false;

  @override
  void initState() {
    super.initState();
    _tourService = ref.read(tourServiceProvider);
    _apiService = ref.read(apiServiceProvider);
    _localStateService = LocalStateService();
    _analytics = ref.read(analyticsServiceProvider);
    _offlineService = ref.read(offlineStorageServiceProvider);
    if (widget.enableRecognition) {
      WidgetsBinding.instance.addPostFrameCallback((_) async {
        if (!mounted) return;
        await Future.delayed(const Duration(milliseconds: 200));
        _initializeCamera();
      });
      _getCurrentLocation();
      if (widget.isOffline) {
        _initOfflineMap();
        _initializeOfflineRecognizer();
      }
    } else {
      _getCurrentLocation();
    }
    _initializeAnimations();
    // _setInitialContent();

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;

      _setInitialContent();

      if (!widget.enableRecognition) {
        _enterStubRecognizedState();
      }
    });
  }

  @override
  void dispose() {
    arSessionManager?.dispose();
    _cameraController?.stopImageStream();
    _cameraController?.dispose();
    _sheetController.dispose();
    _pulseAnimationController.dispose();
    _successAnimationController.dispose();
    _failureAnimationController.dispose();
    unawaited(_offlineRecognitionService?.dispose());
    _clearTempFiles();
    _resourceMetaCache.clear();
    _markdownScrollTimer?.cancel();
    super.dispose();
  }

  String _getRandomRecognitionFailureMessage() {
    if (_recognitionFailureMessages.isEmpty) {
      return "Recognition failed. Please try again.";
    }

    final randomIndex = Random().nextInt(_recognitionFailureMessages.length);
    return _recognitionFailureMessages[randomIndex];
  }

  Future<Map<String, dynamic>> _getResourceWithMetaCache(int waypointId, String resourceType) async {
    final key = "$waypointId:$resourceType";
    final cached = _resourceMetaCache[key];
    if (cached != null) return cached;

    final response = await _tourService.getResourceByWaypointAndType(waypointId, resourceType);
    final map = (response as Map<String, dynamic>);
    _resourceMetaCache[key] = map;
    return map;
  }

  Future<void> _enterStubRecognizedState() async {
    try{
      await _getTourWaypoints();

      final recognizableWaypoints = _waypoints.where((wp) => !wp.isPreliminaryInfo).toList();

      int waypointId = widget.initialWaypointId ?? -1;
      if (waypointId == -1){
        if (recognizableWaypoints.isNotEmpty) waypointId = recognizableWaypoints.first.id;
      }

      Waypoint? wp;
      try {
        wp = recognizableWaypoints.firstWhere((w) => w.id == waypointId);
      } catch(e) {
        wp = null;
      }

      if (wp != null) {
        widget.landmarkName = wp.title;
        widget.landmarkDescription = wp.description;
        widget.landmarkImages = wp.images;
      }

      final Map<String, dynamic> available = {
        "readme" : 0,
        "links" : 0,
        "pdf" : 0,
        "audio" : 0,
        "video" : 0,
        "images" : 0
      };

      if (waypointId != -1) {
        if (widget.isOffline) {
          final imgs = _offlineImagesByWaypoint[waypointId] ?? [];
          if (imgs.isNotEmpty) available["images"] = 1;
          final res = _offlineResourcesByWaypoint[waypointId] ?? {};
          res.forEach((k, v) {
            if (v is String && v.isNotEmpty) available[k] = 1;
          });
        } else {
          final types = ["readme", "links", "images", "video", "pdf", "audio"];

          await Future.wait(
            types.map((t) async {
              try {
                final resp = await _getResourceWithMetaCache(waypointId, t);
                if (resp.isNotEmpty) {
                  if (t == "images") {
                    final imgs = (resp["images"] as List?) ?? const [];
                    if (imgs.isNotEmpty) available["images"] = 1;
                  } else if (t == "links") {
                    final links = (resp["links"] as List?) ?? const [];
                    if (links.isNotEmpty) available["links"] = 1;
                  } else {
                    final url = resp["url"] ?? resp[t];
                    if (url is String && url.isNotEmpty) available[t] = 1;
                  }
                }
              } catch (_) {}
            }),
          );
        }
      }

      setState(() {
        _recognizedWaypointId = waypointId;
        _availableResources = available;
        _currentMarkdownContent = "# ${widget.landmarkName}\n\n${widget.landmarkDescription}";
        _currentActiveContent = MarkdownWidget(
          data: _currentMarkdownContent,
          config: _buildMarkdownConfig(),
          padding: const EdgeInsets.only(top: 0),
          shrinkWrap: true,
        );
        _recognitionState = RecognitionState.success;
      });
      _successAnimationController.reset();
      _successAnimationController.forward();
      _sheetController.animateTo(
        _initialSheetSize + 0.20,
        duration: const Duration(milliseconds: 500),
        curve: Curves.easeInOut,
      );
      _startAROverlayAnimation();
    } catch(e) {
      debugPrint("Error entering stub recognized state: $e");
      _totemBodyNode = null;
      _arNodeToResourceType.clear();
      _showError("tour_initial_content_error".tr());
    }
  }


  void _toggleARMode() async {
    if (_isARMode) {
      // Switching from AR to Standard
      setState(() {
        _isARMode = false;
      });

      arSessionManager?.dispose();
      arSessionManager = null;
      arObjectManager = null;
      arAnchorManager = null;
      _totemSpawned = false;
      _totemBaseNode = null;
      _totemBodyNode = null;
      _totemMarkdownCardNode = null;
      _markdownScrollTimer?.cancel();

      unawaited(_analytics.logEvent(name: "exit_ar_mode", parameters: {"tour_id": widget.tourId, "waypoint_id": _recognizedWaypointId}));

      await Future.delayed(const Duration(milliseconds: 500));
      if (mounted) {
        await _initializeCamera();
      }
    } else {
      final oldController = _cameraController;
      // Switching from Standard to AR

      setState(() {
        _cameraController = null;
        _isCameraInitialized = false;
      });

      await oldController?.dispose();

      await Future.delayed(const Duration(milliseconds: 500));

      if (!mounted) return;

      setState(() {
        _isARMode = true;
      });

      unawaited(_analytics.logEvent(name: "enter_ar_mode", parameters: {"tour_id": widget.tourId, "waypoint_id": _recognizedWaypointId}));
    }
  }

  Future<void> _initOfflineMap() async {
    final dir = await getApplicationDocumentsDirectory();
    final path = '${dir.path}/offline_tours_data/tour_${widget.tourId}/map.pmtiles';
    if (await File(path).exists()) {
      setState(() {
        _pmtilesPath = path;
        _futureTileProvider = PmTilesTileProvider.fromSource(_pmtilesPath!);
      });
    } else {
      debugPrint("PMTiles file not found at $path");
    }
  }

  List<int> _decompressBytes(List<int> rawBytes) {
    if (rawBytes.isEmpty) return [];
    try{
      return ZLibDecoder().decodeBytes(rawBytes);
    } catch (e) {
      try {
        return GZipDecoder().decodeBytes(rawBytes);
      } catch (e2) {
        return rawBytes;
      }
    }
  }

  Future<File?> _loadAndDecompressResource(String sourcePath, bool isLocal, String extension) async {
    if (_cachedResources.containsKey(sourcePath)) {
      final cachedFile = _cachedResources[sourcePath]!;
      if(await cachedFile.exists()) {
        debugPrint("Using cached resource for $sourcePath");
        return cachedFile;
      } else {
        _cachedResources.remove(sourcePath);
      }
    }

    try {
      List<int> rawBytes;

      if (isLocal) {
        //OFFLINE
        final file = File(sourcePath);
        if(!await file.exists()) {
          throw Exception("File not found at $sourcePath");
        }
        rawBytes = await file.readAsBytes();
      } else {
        //ONLINE
        String url = sourcePath.startsWith("http") ? sourcePath : "${_apiService.getCurrentBaseUrl()}$sourcePath";

        final response = await Dio().get(
          url,
          options: Options(responseType: ResponseType.bytes),
        );

        if (response.statusCode == 200){
          rawBytes = response.data ?? [];
        }else{
          throw Exception("Failed to download resource from $sourcePath, status code: ${response.statusCode}");
        }
      }

      //DECOMPRESSIONE
      final List<int> decompressedBytes = _decompressBytes(rawBytes);
      final tempDir = await getTemporaryDirectory();
      final tempFile = File('${tempDir.path}/decompressed_resource_${DateTime.now().millisecondsSinceEpoch}.$extension');
      await tempFile.writeAsBytes(decompressedBytes, flush: true);

      _tempFiles.add(tempFile);
      _cachedResources[sourcePath] = tempFile;

      debugPrint("Decompressed resource saved to ${tempFile.path}");
      return tempFile;

    } catch(e) {
      debugPrint("Error during handling of ZLib Resource: $e");
      _showError("error_loading_resource".tr());
      return null;
    }
  }

  Future<void> _clearTempFiles() async {
    for(var file in _tempFiles) {
      try{
        if (await file.exists()) {
          await file.delete();
          debugPrint("Deleted temp file: ${file.path}");
        }
      } catch(e) {
        debugPrint("Error deleting temp file ${file.path}: $e");
      }
    }
    _tempFiles.clear();
  }

  Widget _baseMapLayer() {
    if (widget.isOffline && _pmtilesPath != null) {
      return FutureBuilder<PmTilesTileProvider>(
        future: _futureTileProvider,
        builder: (context, snapshot) {
          if (snapshot.hasData) {
            return TileLayer(
              tileProvider: snapshot.data!,
              urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
            );
          }
          // You might want to show a loader or a fallback here
          // return const SizedBox.shrink();
          if (snapshot.hasError) {
            debugPrint(snapshot.error.toString());
            debugPrintStack(stackTrace: snapshot.stackTrace);
            return Center(child: Text(snapshot.error.toString()));
          }
          return const Center(child: CircularProgressIndicator());
        },
      );
    }

    return TileLayer(
      urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
      userAgentPackageName: 'com.picaresque.xrtourguide',
      tileProvider: NetworkTileProvider(),
    );
  }

  Future<void> _initializeOfflineRecognizer() async {
    try {
      _offlineRecognitionService = OfflineRecognitionIsolateService();

      await _offlineRecognitionService!.init(
        tourId: widget.tourId,
        modelAssetPath: 'assets/models/EfficientNetLite0.tflite',
      );

      debugPrint('Offline recognizer isolate initialized for tour ${widget.tourId}');
    } catch (e) {
      debugPrint('Error initializing offline recognizer isolate: $e');
      _showError('error_initializing_recognizer'.tr());
    }
  }

  // Initialize camera
  Future<void> _initializeCamera() async {
    if (_isARMode) return;
    try {

      final status = await Permission.camera.status;
      if (status.isPermanentlyDenied) {
        _showError('camera_permission_error'.tr());
        await openAppSettings();
        return;
      }
      final camStatus = await Permission.camera.request();
      debugPrint("Camera permission status: $camStatus");
      if (!camStatus.isGranted) {
        _showError('camera_permission_error'.tr());
        return;
      }

      _cameras = await availableCameras();
      debugPrint("Available cameras: ${_cameras!.map((c) => c.name).join(", ")}");
      if (_cameras != null && _cameras!.isNotEmpty) {
        final controller = CameraController(
          _cameras![0], // Use the first camera (usually back camera)
          ResolutionPreset.high,
          enableAudio: false,
          imageFormatGroup: ImageFormatGroup.yuv420,
        );


        await controller.initialize();
        _minZoomLevel = await controller.getMinZoomLevel();
        _maxZoomLevel = await controller.getMaxZoomLevel();
        _currentZoomLevel = _minZoomLevel;
        await controller.setZoomLevel(_currentZoomLevel);
        if (!mounted) return;

        if (_isARMode) {
          await controller.dispose();
          return;
        }


        if (mounted) {
          setState(() {
            _cameraController = controller;
            _isCameraInitialized = true;
          });
        }

      }
    } catch (e) {
      debugPrint('Error initializing camera: $e');
    }
  }

  void _handleScaleStart(ScaleStartDetails details) {
    _baseZoomLevel = _currentZoomLevel;
  }

  Future<void> _handleScaleUpdate(ScaleUpdateDetails details) async {
    if (_cameraController == null || !_isCameraInitialized) return;

    final newZoom = (_baseZoomLevel * details.scale).clamp(_minZoomLevel, _maxZoomLevel);

    if ((newZoom - _currentZoomLevel).abs() < 0.02) return;

    _currentZoomLevel = newZoom;
    await _cameraController!.setZoomLevel(_currentZoomLevel);

    if (mounted) {
      setState(() {});
    }
  }

  void onARViewCreated(
    ARSessionManager sessionManager,
    ARObjectManager objectManager,
    ARAnchorManager anchorManager,
    ARLocationManager locationManager){

      arSessionManager = sessionManager;
      arObjectManager = objectManager;
      arAnchorManager = anchorManager;

      arSessionManager!.onInitialize(
        showFeaturePoints: true,
        showPlanes: true,
        showWorldOrigin: false,
        handlePans: false,
        handleRotation: false,
        handleTaps: true,
      );

      arObjectManager!.onInitialize(
        androidScaleFactor: 1.0,
        iosScaleFactor: 0.01,
      );

      arSessionManager!.onPlaneOrPointTap = _onPlaneTap;
  }

  Future<void> _onPlaneTap(List<ARHitTestResult> hits) async {
    if (_recognitionState != RecognitionState.success || _totemSpawned) {
      if(_recognitionState != RecognitionState.success) {
        _showError("firs_recognition".tr());
      }
      return;
    }

    // var hit = hits.firstWhere((element) => element.type == ARHitTestResultType.plane);
    final planeHits = hits.where((h) => h.type == ARHitTestResultType.plane).toList();
    if (planeHits.isEmpty) {
      _showError("ar_instruction".tr());
      return;
    }
    final hit = planeHits.first;
    var anchor = ARPlaneAnchor(transformation: hit.worldTransform);
    bool? didAddAnchor = await arAnchorManager?.addAnchor(anchor);

    if (didAddAnchor == true) {
      setState(() {
        _totemSpawned = true;
      });
      // arSessionManager!.onInitialize(showPlanes: false);
      // arSessionManager?.showPlanes(false);
      _spawnAndAnimateTotem(anchor);
    }
  }

  Future<void> _spawnAndAnimateTotem(ARPlaneAnchor anchor) async {
    final manager = arObjectManager;
    if (manager == null) return;

    final cfg = arPlatformCfg;
    final double initialVisualScale =
        _totemStartScale * cfg.modelScaleCompensation;

    final structureNode = ARNode(
      type: NodeType.localGLB,
      uri: "assets/models/AR/totem_base/totem_base.glb",
      scale: vector.Vector3(
        initialVisualScale,
        initialVisualScale,
        initialVisualScale,
      ),
      position: vector.Vector3(0, cfg.totemOffsetY, 0),
      rotation: vector.Vector4(1.0, 0.0, 0.0, 0.0),
    );

    final bool? didAddBase = await manager.addNode(
      structureNode,
      planeAnchor: anchor,
    );

    if (didAddBase != true) {
      _totemSpawned = false;
      debugPrint("[DEBUG] Failed to add Totem Base Node");
      return;
    }

    _totemBaseNode = structureNode;

    final vector.Vector4 totemBodyRotation = Platform.isIOS
      ? vector.Vector4(1.0, 0.0, 0.0, 0.0)
      : vector.Vector4(1.0, 0.0, 0.0, 0.0);

    final String totemBodyUri = Platform.isIOS
      ? "assets/models/AR/totem_body/totem_body_ios.glb"
      : "assets/models/AR/totem_body/totem_body.glb";

    final bodyNode = ARNode(
      type: NodeType.localGLB,
      uri: totemBodyUri,
      scale: vector.Vector3(
        initialVisualScale,
        initialVisualScale,
        initialVisualScale,
      ),
      position: vector.Vector3(0, cfg.totemOffsetY, 0),
      rotation: totemBodyRotation,
    );

    final bool? didAddBody = await manager.addNode(
      bodyNode,
      planeAnchor: anchor,
    );

    if (didAddBody == true) {
      _totemBodyNode = bodyNode;
    } else {
      debugPrint("[DEBUG] Failed to add Totem Body Node");
    }

    // Crescita "logica" identica tra piattaforme.
    double currentLogicalScale = 0.01;

    Timer.periodic(const Duration(milliseconds: 20), (timer) {
      if (!mounted || _totemBaseNode == null) {
        timer.cancel();
        return;
      }

      currentLogicalScale += 0.1;
      if (currentLogicalScale >= _totemTargetScale) {
        currentLogicalScale = _totemTargetScale;
        timer.cancel();
        _spawnTotemMarkdownCard(anchor, currentLogicalScale);
      }

      final double visualScale =
          currentLogicalScale * cfg.modelScaleCompensation;

      final nextScale = vector.Vector3(visualScale, visualScale, visualScale);
      _totemBaseNode?.scale = nextScale;
      _totemBodyNode?.scale = nextScale;
    });
  }

  Future<void> _spawnTotemMarkdownCard(
    ARPlaneAnchor anchor,
    double logicalTotemScale,
  ) async {
    final manager = arObjectManager;
    if (manager == null) return;

    final cfg = arPlatformCfg;

    final String title =
        widget.landmarkName.trim().isNotEmpty
            ? widget.landmarkName.trim()
            : "Waypoint";

    final String readmeMarkdown = await _loadReadmeMarkdownForTotem();

    _markdownMaxScrollOffset = _calculateMarkdownMaxScrollOffset(
      readmeMarkdown,
    );

    final String cardGltfPath = await _createTotemMarkdownCardGltf(
      title: title,
      markdown: readmeMarkdown,
      scrollOffset: 0,
      frameIndex: 0,
    );

    final double cardScale = 0.2 * cfg.modelScaleCompensation;
    final double cardScaleIOS = 20 * cfg.modelScaleCompensation;
    final vector.Vector3 cardPosition = Platform.isIOS
      ? vector.Vector3(-0.01, 0.9, 0.03)
      : vector.Vector3(-0.01, 0.9, -0.03);
    final vector.Vector4 cardRotation = Platform.isIOS
        ? vector.Vector4(0.0, 1.0, 0.0, 0.0)
        : vector.Vector4(1.0, 0.0, 0.0, 0.0);
    final vector.Vector3 cardScaleVector = Platform.isIOS
      ? vector.Vector3(cardScaleIOS, cardScaleIOS, cardScaleIOS)
      : vector.Vector3(cardScale , cardScale, cardScale);

    final cardNode = ARNode(
      type: NodeType.fileSystemAppFolderGLTF2,
      uri: cardGltfPath,
      scale: cardScaleVector,
      position: cardPosition,
      rotation: cardRotation,
      name: "[#]totem_markdown_card",
    );

    final bool? didAdd = await manager.addNode(cardNode, planeAnchor: anchor);

    debugPrint(
      '[AR DEBUG] Markdown panel didAdd=$didAdd, '
      'maxScroll=$_markdownMaxScrollOffset, '
      'position=$cardPosition, '
      'scale=$cardScale',
    );

    if (didAdd == true) {
      _totemMarkdownCardNode = cardNode;

      if (mounted) {
        setState(() {
          _currentActiveContent = _buildResourceButtonsContent();
        });
      }

      _sheetController.animateTo(
        _initialSheetSize + 0.15,
        duration: const Duration(milliseconds: 300),
        curve: Curves.easeInOut,
      );

      if (_markdownMaxScrollOffset > 8) {
        _startMarkdownAutoScroll(
          anchor: anchor,
          title: title,
          markdown: readmeMarkdown,
          maxScrollOffset: _markdownMaxScrollOffset,
        );
      }
    } else {
      debugPrint("[DEBUG] Failed to add Totem Markdown Card Node");
    }
  }

  Future<String> _loadReadmeMarkdownForTotem() async {
    try {
      Map<String, dynamic> content = {};

      if (widget.isOffline) {
        final resources =
            _offlineResourcesByWaypoint[_recognizedWaypointId] ?? {};
        content = {'readme': resources['readme']};
      } else {
        content = await _getResourceWithMetaCache(
          _recognizedWaypointId,
          'readme',
        );

        if (content.containsKey('url')) {
          content['readme'] = content['url'];
        }
      }

      final String readmePath = (content['readme'] ?? '').toString();

      if (readmePath.isEmpty) {
        return widget.landmarkDescription.trim().isNotEmpty
            ? widget.landmarkDescription.trim()
            : 'Nessun contenuto markdown disponibile.';
      }

      final File? textFile = await _loadAndDecompressResource(
        readmePath,
        widget.isOffline,
        'md',
      );

      if (textFile == null) {
        return widget.landmarkDescription.trim().isNotEmpty
            ? widget.landmarkDescription.trim()
            : 'Errore nel caricamento del contenuto markdown.';
      }

      return await textFile.readAsString();
    } catch (e) {
      debugPrint('[AR DEBUG] Error loading readme markdown for totem: $e');

      return widget.landmarkDescription.trim().isNotEmpty
          ? widget.landmarkDescription.trim()
          : 'Errore nel caricamento del contenuto markdown.';
    }
  }

  Future<String> _createTotemMarkdownCardGltf({
      required String title,
      required String markdown,
      required double scrollOffset,
      required int frameIndex,
    }) async {
      final Directory dir = await getApplicationDocumentsDirectory();

      final Directory cardDir = Directory('${dir.path}/ar_markdown_card');
      if (!await cardDir.exists()) {
        await cardDir.create(recursive: true);
      }

      final String pngFileName = 'totem_markdown_card_$frameIndex.png';
      final String gltfFileName = 'totem_markdown_card_$frameIndex.gltf';

      final String pngPath = '${cardDir.path}/$pngFileName';
      final String gltfPath = '${cardDir.path}/$gltfFileName';

      // final String title = widget.landmarkName.trim();
      // final String readmeMarkdown = await _loadReadmeMarkdownForTotem();

      final Uint8List pngBytes = await _renderTotemMarkdownCardPng(
        title: title,
        markdown: markdown,
        scrollOffset: scrollOffset,
      );

      await File(pngPath).writeAsBytes(pngBytes, flush: true);

      final String gltf = _buildTexturedCardPlaneGltf(imageFileName: pngFileName);

      await File(gltfPath).writeAsString(gltf, flush: true);

      if (Platform.isIOS) {
        return 'ar_markdown_card/$gltfFileName';
      }
      return gltfPath;
    }

  double _calculateMarkdownMaxScrollOffset(String markdown) {
    const double width = 740;
    const double height = 1000;

    const Rect bodyRect = Rect.fromLTWH(36, 150, width - 72, height - 190);

    final String cleanedMarkdown = _cleanMarkdownForTotem(markdown);

    final TextPainter bodyPainter = TextPainter(
      text: TextSpan(
        text: cleanedMarkdown,
        style: const TextStyle(color: Colors.black, fontSize: 30, height: 1.20),
      ),
      textDirection: ui.TextDirection.ltr,
    );

    bodyPainter.layout(maxWidth: bodyRect.width);

    final double overflow = bodyPainter.height - bodyRect.height;

    return overflow > 0 ? overflow : 0.0;
  }

  Future<Uint8List> _renderTotemMarkdownCardPng({
    required String title,
    required String markdown,
    required double scrollOffset,
  }) async {
    const double width = 740;
    const double height = 1000;

    final ui.PictureRecorder recorder = ui.PictureRecorder();
    final Canvas canvas = Canvas(recorder);

    final Paint backgroundPaint = Paint() ..color = Colors.white;

    canvas.drawRRect(
      RRect.fromRectAndRadius(
        const Rect.fromLTWH(0, 0, width, height),
        const Radius.circular(40),
      ),
      backgroundPaint,
    );

    final Paint borderPaint = Paint()
      ..color = const Color(0xFF222222)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 4.0;

    canvas.drawRRect(
      RRect.fromRectAndRadius(
        const Rect.fromLTWH(8, 8, width - 16, height - 16),
        const Radius.circular(34),
      ),
      borderPaint,
    );

    final TextPainter titlePainter = TextPainter(
      text: TextSpan(
        text: title,
        style: const TextStyle(
          color: Colors.black,
          fontSize: 46,
          fontWeight: FontWeight.bold,
          height: 1.05,
        ),
      ),
      textDirection: ui.TextDirection.ltr,
      maxLines: 2,
      ellipsis: '...',
    );

    titlePainter.layout(maxWidth: width - 72);
    titlePainter.paint(canvas, const Offset(36, 40));

    final String cleanedMarkdown = _cleanMarkdownForTotem(markdown);

    const Rect bodyRect = Rect.fromLTWH(36, 150, width - 72, height - 190);

    canvas.save();
    canvas.clipRect(bodyRect);

    final TextPainter bodyPainter = TextPainter(
      text: TextSpan(
        text: cleanedMarkdown,
        style: const TextStyle(color: Colors.black, fontSize: 30, height: 1.20),
      ),
      textDirection: ui.TextDirection.ltr,
    );

    bodyPainter.layout(maxWidth: bodyRect.width);

    bodyPainter.paint(
      canvas,
      Offset(bodyRect.left, bodyRect.top - scrollOffset),
    );

    canvas.restore();
    final ui.Picture picture = recorder.endRecording();
    final ui.Image image = await picture.toImage(
      width.toInt(),
      height.toInt(),
    );

    final ByteData? byteData = await image.toByteData(format: ui.ImageByteFormat.png);

    return byteData!.buffer.asUint8List();
  }

  void _startMarkdownAutoScroll({
    required ARPlaneAnchor anchor,
    required String title,
    required String markdown,
    required double maxScrollOffset,
  }) {
    _markdownScrollTimer?.cancel();

    double scrollOffset = 0.0;
    _markdownScrollFrame = 0;
    _markdownScrollDown = true;

    int pauseTicks = 0;

    _markdownScrollTimer = Timer.periodic(const Duration(milliseconds: 700), (
      timer,
    ) async {
      if (!mounted || arObjectManager == null) {
        timer.cancel();
        return;
      }

      final oldNode = _totemMarkdownCardNode;
      if (oldNode == null) {
        timer.cancel();
        return;
      }

      if (pauseTicks > 0) {
        pauseTicks--;
        return;
      }

      const double step = 24.0;

      if (_markdownScrollDown) {
        scrollOffset += step;

        if (scrollOffset >= maxScrollOffset) {
          scrollOffset = maxScrollOffset;
          _markdownScrollDown = false;
          pauseTicks = 3;
        }
      } else {
        scrollOffset -= step;

        if (scrollOffset <= 0) {
          scrollOffset = 0;
          _markdownScrollDown = true;
          pauseTicks = 3;
        }
      }

      _markdownScrollFrame++;

      final String cardGltfPath = await _createTotemMarkdownCardGltf(
        title: title,
        markdown: markdown,
        scrollOffset: scrollOffset,
        frameIndex: _markdownScrollFrame,
      );

      final cfg = arPlatformCfg;
      final double cardScale = 0.2 * cfg.modelScaleCompensation;
      final vector.Vector3 cardPosition = vector.Vector3(-0.01, 0.9, -0.03);
      final vector.Vector4 cardRotation = Platform.isIOS
          ? vector.Vector4(0.0, 1.0, 0.0, 0.0)
          : vector.Vector4(1.0, 0.0, 0.0, 0.0);

      arObjectManager!.removeNode(oldNode);

      final newNode = ARNode(
        type: NodeType.fileSystemAppFolderGLTF2,
        uri: cardGltfPath,
        scale: vector.Vector3(cardScale, cardScale, cardScale),
        position: cardPosition,
        rotation: cardRotation,
        name: "[#]totem_markdown_card_$_markdownScrollFrame",
      );

      final bool? didAdd = await arObjectManager!.addNode(
        newNode,
        planeAnchor: anchor,
      );

      if (didAdd == true) {
        _totemMarkdownCardNode = newNode;
      }
    });
  }

  String _cleanMarkdownForTotem(String markdown) {
    return markdown
        .replaceAll(RegExp(r'!\[[^\]]*\]\([^)]+\)'), '')
        .replaceAll(RegExp(r'\[([^\]]+)\]\([^)]+\)'), r'$1')
        .replaceAll(RegExp(r'#{1,6}\s*'), '')
        .replaceAll(RegExp(r'[*_`>~]'), '')
        .replaceAll(RegExp(r'\n{3,}'), '\n\n')
        .trim();
  }

  String _buildTexturedCardPlaneGltf({required String imageFileName}) {
    final ByteData data = ByteData(92);

    int offset = 0;

    void writeFloat(double value) {
      data.setFloat32(offset, value, Endian.little);
      offset += 4;
    }

    void writeUint16(int value) {
      data.setUint16(offset, value, Endian.little);
      offset += 2;
    }

    // POSITION: 4 vertices, aspect ratio 4:3.
    final List<double> positions = [
      -1.0, 1.35, 0.0,
      1.0, 1.35, 0.0,
      1.0, -1.35, 0.0,
      -1.0, -1.35, 0.0,
    ];

    for (final double value in positions) {
      writeFloat(value);
    }

    // TEXCOORD_0
    // final List<double> uvs = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0];
    final List<double> uvs =
        Platform.isIOS
            ? [0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0]
            : [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0];

    for (final double value in uvs) {
      writeFloat(value);
    }

    // Indices
    final List<int> indices = [0, 2, 1, 0, 3, 2];

    for (final int value in indices) {
      writeUint16(value);
    }

    final String bufferBase64 = base64Encode(data.buffer.asUint8List());

    return '''
{
  "asset": {
    "version": "2.0"
  },
  "scene": 0,
  "scenes": [
    {
      "nodes": [0]
    }
  ],
  "nodes": [
    {
      "mesh": 0,
      "name": "totem_markdown_card"
    }
  ],
  "meshes": [
    {
      "primitives": [
        {
          "attributes": {
            "POSITION": 0,
            "TEXCOORD_0": 1
          },
          "indices": 2,
          "material": 0
        }
      ]
    }
  ],
  "materials": [
    {
      "name": "card_material",
      "doubleSided": true,
      "alphaMode": "BLEND",
      "pbrMetallicRoughness": {
        "baseColorTexture": {
          "index": 0
        },
        "baseColorFactor": [1.0, 1.0, 1.0, 1.0],
        "metallicFactor": 0.0,
        "roughnessFactor": 0.8
      }
    }
  ],
  "textures": [
    {
      "source": 0
    }
  ],
  "images": [
    {
      "uri": "$imageFileName"
    }
  ],
  "buffers": [
    {
      "uri": "data:application/octet-stream;base64,$bufferBase64",
      "byteLength": 92
    }
  ],
  "bufferViews": [
    {
      "buffer": 0,
      "byteOffset": 0,
      "byteLength": 48,
      "target": 34962
    },
    {
      "buffer": 0,
      "byteOffset": 48,
      "byteLength": 32,
      "target": 34962
    },
    {
      "buffer": 0,
      "byteOffset": 80,
      "byteLength": 12,
      "target": 34963
    }
  ],
  "accessors": [
    {
      "bufferView": 0,
      "componentType": 5126,
      "count": 4,
      "type": "VEC3",
      "min": [-1.0, -1.35, 0.0],
      "max": [1.0, 1.35, 0.0]
    },
    {
      "bufferView": 1,
      "componentType": 5126,
      "count": 4,
      "type": "VEC2"
    },
    {
      "bufferView": 2,
      "componentType": 5123,
      "count": 6,
      "type": "SCALAR"
    }
  ]
}
''';
  }

  final Map<String, String> _arNodeToResourceType = {};

  void _handleRecognitionSuccess(int waypointId, Map<String, dynamic> availableResources, bool isOffline) async {

    _waypoints.forEach((waypoint) {
      if (waypoint.id == waypointId && waypoint.subWaypoints == null) {
        widget.landmarkName = waypoint.title;
        widget.landmarkImages = waypoint.images;
        widget.landmarkDescription = waypoint.description;
      }
    });

    _pulseAnimationController.stop();

    setState(() {
      _recognizedWaypointId = waypointId;
      _availableResources = availableResources;
      _currentMarkdownContent = "# ${widget.landmarkName}\n\n${widget.landmarkDescription}";
      _currentActiveContent = MarkdownWidget(
        data: _currentMarkdownContent,
        config: _buildMarkdownConfig(),
        padding: const EdgeInsets.only(top: 0),
        shrinkWrap: true,
      );
      _recognitionState = RecognitionState.success;
    });
    _successAnimationController.reset();
    _successAnimationController.forward();

    _startAROverlayAnimation();
    // await _checkTourCompletion();
  }

  // Helper to build MarkdownConfig once
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
            debugPrint("Loading image from URL: $url");

            if (url.startsWith('file://')) {
              String localPath;
              try {
                localPath = Uri.parse(url).toFilePath();
              } catch (e) {
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
                      return Container(
                        height: 180,
                        width: double.infinity,
                        decoration: BoxDecoration(
                          color: Colors.grey.shade300,
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Icon(
                          Icons.image_not_supported,
                          color: Colors.grey.shade600,
                        ),
                      );
                    },
                  ),
                ),
              );
            }

            return Container(
              margin: const EdgeInsets.symmetric(vertical: 8),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(12),
                child: CachedNetworkImage(
                  imageUrl: url,
                  fit: BoxFit.cover,
                  memCacheWidth: 1200,
                  maxWidthDiskCache: 1600,
                  placeholder:
                      (context, url) => const Center(
                        child: CircularProgressIndicator(strokeWidth: 2),
                      ),
                  errorWidget: (context, url, error) {
                    return Container(
                      height: 180,
                      width: double.infinity,
                      decoration: BoxDecoration(
                        color: Colors.grey.shade300,
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Icon(
                        Icons.image_not_supported,
                        color: Colors.grey.shade600,
                      ),
                    );
                  },
                ),
              ),
            );
          },
        ),
        BlockquoteConfig(
          sideColor: AppColors.primary.withOpacity(0.5),
          textColor: AppColors.textSecondary.withOpacity(0.8),
          sideWith: 4.0,
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
          margin: const EdgeInsets.symmetric(vertical: 8),
        ),
      ],
    );
  }

  void _showError(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), backgroundColor: Colors.red),
    );
  }


  Future<void> _getTourWaypoints() async{
    if (!widget.isOffline) {
      try {
        final waypoints = await _tourService.getWaypointsByTour(widget.tourId);
        if (mounted) {
          setState(() {
            _waypoints = [];
            for (var waypoint in waypoints) {
              if (!waypoint.isPreliminaryInfo) {
                _waypoints.add(waypoint);
              }
              if (waypoint.subWaypoints != null){
                _waypoints.addAll(waypoint.subWaypoints!);
              }
            }
            _isLoadingWaypoints = false;
          });
        }
      } catch (e) {
        if (mounted){
          setState(() {
            _isLoadingWaypoints = false;
          });
        }
        _showError('error_loading_waypoints'.tr());
      }
    } else {
      try {
        final offlineData = await _offlineService.getOfflineTourData(widget.tourId);
        if (offlineData != null) {
          final List wps = (offlineData['waypoints'] as List?) ?? [];
          final List subTours = (offlineData['sub_tours'] as List?) ?? [];

          final List<Waypoint> mainWaypoints = wps.map<Waypoint>((wp) => Waypoint.fromJson(wp as Map<String, dynamic>)).toList();
          mainWaypoints.sort(Waypoint.compareByPosition);

          final List<Waypoint> subTourWaypoints = <Waypoint>[];

          for (final st in subTours) {
            final subTourInfo = st['sub_tour'] as Map<String, dynamic>?;
            if (subTourInfo == null) continue;

            final subWpJson = (st['waypoints'] as List?) ?? [];
            final subWps = subWpJson.map<Waypoint>((wp) => Waypoint.fromJson(wp as Map<String, dynamic>)).toList();
            subWps.sort(Waypoint.compareByPosition);

            subTourWaypoints.addAll(subWps);
          }

          debugPrint("Loading images and resources for offline waypoints...");

          final Map<int, List<String>> imagesByWp = {};
          final Map<int, Map<String, dynamic>> resourcesByWp = {};
          for (final wp in wps) {
            final id = (wp['id'] as num).toInt();
            final localImages =
                (wp['local_images'] as List?)?.cast<String>() ?? <String>[];
            final local_resources = wp["local_resources"] as Map<String, dynamic>?;

            imagesByWp[id] = localImages;
            resourcesByWp[id] = local_resources!;
          }
          for (final st in subTours) {
            final List subWp = (st['waypoints'] as List?) ?? [];
            for (final wp in subWp) {
              final id = (wp['id'] as num).toInt();
              final localImages = (wp['local_images'] as List?)?.cast<String>() ?? <String>[];
              final local_resources = wp["local_resources"] as Map<String, dynamic>?;

              imagesByWp[id] = localImages;
              resourcesByWp[id] = local_resources!;
            }
          }


          if (mounted) {
            setState(() {
              _waypoints = [...mainWaypoints, ...subTourWaypoints]
                ..sort(Waypoint.compareByPosition);
              _offlineImagesByWaypoint = imagesByWp;
              _offlineResourcesByWaypoint = resourcesByWp;
              _isLoadingWaypoints = false;
            });
          }
        }
      } catch (e) {
        if (mounted) {
          setState(() {
            _isLoadingWaypoints = false;
          });
        }
        debugPrint("Failed to load offline waypoints: $e");
        _showError('error_loading_waypoints'.tr());

      }
    }
  }

  // Set the initial content for the draggable sheet
  void _setInitialContent() {
    _getTourWaypoints();

    setState(() {
      _currentMarkdownContent = """ 
      """;
      _currentActiveContent = MarkdownWidget(
        data: _currentMarkdownContent,
        config: _buildMarkdownConfig(),
        padding: const EdgeInsets.only(top: 0),
        shrinkWrap: true,
      );
    });
  }

  String _processImageContent(String content) {
    if (content.isEmpty) return content;

    String baseUrl = _apiService.getCurrentBaseUrl();

    List<String> lines = content.split('\n');

    List<String> processedLines =
        lines.map((line) {
          line = line.trim();

          if (line.startsWith('![') &&
              line.contains('](/stream_minio_resource/')) {
            RegExp regex = RegExp(
              r'!\[(\d+)\]\((/stream_minio_resource/[^)]+)\)',
            );
            Match? match = regex.firstMatch(line);

            if (match != null) {
              String imageNumber = match.group(1)!;
              String imagePath = match.group(2)!;

              return '![$imageNumber]($baseUrl$imagePath)';
            }
          }

          return line;
        }).toList();

    // Ricomponi il contenuto
    return processedLines.join('\n');
  }

  // Update draggable sheet content based on type
  Future<void> _updateDraggableSheetContent(String type, int waypointId) async {
    // This will hold the content that goes into the _currentActiveContent
    Widget? contentToDisplay;
    Map<String, dynamic> content = {};

    unawaited(_analytics.logEvent(name: "content_viewed", parameters: {"tour_id": widget.tourId, "waypoint_id": waypointId, "content_type": type, "is_offline": widget.isOffline}));

    var queryType = type;
    if (type == "text"){
      queryType = "readme";
    }
    if (type == "link") {
      queryType = "links";
    }
    if (type == "document") {
      queryType = "pdf";
    }
    if (type == "image"){
      queryType = "images";
    }

    try {
      if (widget.isOffline) {
        final resources = _offlineResourcesByWaypoint[waypointId] ?? {};
        final images = _offlineImagesByWaypoint[waypointId] ?? [];

        // Crea un oggetto content con i path locali
        content = {
          'readme': resources['readme'],
          'links': resources['links'],
          'pdf': resources['pdf'],
          'video': resources['video'],
          'audio': resources['audio'],
          'images': images, // Lista di path immagini locali
        };

      } else {
        // final response = await _tourService.getResourceByWaypointAndType(
        //   waypointId,
        //   queryType,
        // );
        // content = response as Map<String, dynamic>;
        content = await _getResourceWithMetaCache(waypointId, queryType);
        if(content.containsKey("url")){
          content[queryType] = content["url"];
        }
        debugPrint("Retrieved content for waypoint $waypointId, type $queryType: $content");
      }
    } catch (e) {
      debugPrint("error retrieving content: $e");
      type = 'error';
    }

    setState(() {
      _currentActiveContent = const Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            CircularProgressIndicator(),
            SizedBox(height: 16),
            Text(
              'Loading content...',
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

    switch (type) {
      case 'text':
        final readmePath = content['readme'] ?? '';
        debugPrint("Readme path: $readmePath");
        if (readmePath.isNotEmpty) {
          File? textFile = await _loadAndDecompressResource(
            readmePath,
            widget.isOffline,
            'md',
          );

          if(textFile != null){
            _currentMarkdownContent = await textFile.readAsString();
          } else {
            _currentMarkdownContent = 'Error loading readme content.';
          }
        } else {
          _currentMarkdownContent = 'No readme available for this waypoint.';
        }

        contentToDisplay = MarkdownWidget(
          data: _currentMarkdownContent,
          config: _buildMarkdownConfig(),
          padding: const EdgeInsets.only(top: 0),
          shrinkWrap: true,
        );
        break;

      case 'link':
        List<String> linksList = [];

        if (widget.isOffline) {
          final linksData = content['links'];
          String linksContent = '';

          if (linksData is String && linksData.isNotEmpty) {
            // È un percorso file, proviamo a leggerlo
            try {
              final file = File(linksData);
              if (await file.exists()) {
                String fileContent = await file.readAsString();
                try {
                  var decoded = jsonDecode(fileContent);
                  if (decoded is List) {
                    linksList = decoded.map((e) => e.toString()).toList();
                  }
                } catch (e) {
                  debugPrint("Error decoding links JSON: $e");
                  if (fileContent.isNotEmpty) {
                    linksList = fileContent.split('\n').where((line) => line.trim().isNotEmpty).toList();
                  }
                }
              } 
              } catch (e) {
                debugPrint("Error reading links file: $e");
              }
            }
          } else {
            linksList = (content['links'] as List?)?.cast<String>() ?? [];
          }

        debugPrint("Links list: $linksList");

        if(linksList.isNotEmpty) {
          StringBuffer mdBuffer = StringBuffer("# ${widget.landmarkName} Links\n\n");

          for (String link in linksList) {
            mdBuffer.writeln("- [${link}](${link})\n");
          }

          _currentMarkdownContent = mdBuffer.toString();
        } else {
          _currentMarkdownContent = "# ${widget.landmarkName}\n\nNo links available for this waypoint.";
        }
        


        contentToDisplay = MarkdownWidget(
          data: _currentMarkdownContent,
          config: _buildMarkdownConfig(),
          padding: const EdgeInsets.only(top: 0),
          shrinkWrap: true,
        );
        break;

      case 'image':
        final imagesList = (content['images'] as List?)?.cast<String>() ?? [];
        debugPrint("Images list: $imagesList");

        if (imagesList.isNotEmpty) {
          StringBuffer mdBuffer = StringBuffer("# ${widget.landmarkName}\n\n");

          for (final imgPath in imagesList) {
            final markdownImageUrl = widget.isOffline
                ? Uri.file(imgPath).toString()
                : imgPath.startsWith("http")
                    ? imgPath
                    : "${_apiService.getCurrentBaseUrl()}$imgPath";

            mdBuffer.writeln("![Image]($markdownImageUrl)\n\n");
          }

          _currentMarkdownContent = mdBuffer.toString();

        } else {
          _currentMarkdownContent = "# ${widget.landmarkName}\n\nNo images available for this waypoint.";
        }

        contentToDisplay = MarkdownWidget(
          data: _currentMarkdownContent,
          config: _buildMarkdownConfig(),
          padding: const EdgeInsets.only(top: 0),
          shrinkWrap: true,
        );
        break;
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

      case 'audio':
        final audioPath = content['audio'] ?? '';
        debugPrint("Audio path: $audioPath");
        if (audioPath.isNotEmpty) {
          File? audioFile = await _loadAndDecompressResource(
            audioPath,
            widget.isOffline,
            'mp3',
          );

          if (audioFile != null) {
            contentToDisplay = AudioPlayerWidget(
              audioUrl: audioFile.path,
              isLocalFile: true, //Sempre true perché è un file locale temporaneo
            );
          } else {
            contentToDisplay = const Center(child: Text("Errore nel caricamento dell'audio"));
          }

        } else {
          contentToDisplay = const Center(
            child: Text(
              'No audio available for this waypoint.',
              style: TextStyle(color: AppColors.textPrimary),
            ),
          );
        }
        break;

      case 'error':
        contentToDisplay = Center(
          child: Text(
            'No content available for "$queryType".',
            style: const TextStyle(color: AppColors.textPrimary),
          ),
        );
    }

    _sheetController.animateTo(
      _initialSheetSize + 0.25,
      duration: const Duration(milliseconds: 300),
      curve: Curves.easeInOut,
    );

    if (mounted && contentToDisplay != null){
      // setState(() {
      //   _currentActiveContent = contentToDisplay;
      // });
      setState(() {
        _currentActiveContent = Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            TextButton.icon(
              onPressed: () {
                setState(() {
                  _currentActiveContent = _buildResourceButtonsContent();
                });
              },
              icon: const Icon(Icons.arrow_back),
              label: const Text('Risorse'),
            ),
            const SizedBox(height: 8),
            contentToDisplay!,
          ],
        );
      });
    }
  }

  // Initialize animations
  void _initializeAnimations() {
    // Pulse animation for scanning state
    _pulseAnimationController = AnimationController(
      duration: const Duration(milliseconds: 1500),
      vsync: this,
    );
    _pulseAnimation = Tween<double>(begin: 0.8, end: 1.2).animate(
      CurvedAnimation(
        parent: _pulseAnimationController,
        curve: Curves.easeInOut,
      ),
    );

    // Success animation
    _successAnimationController = AnimationController(
      duration: const Duration(milliseconds: 1200),
      vsync: this,
    );
    _successAnimation = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(
        parent: _successAnimationController,
        curve: Curves.easeOut,
      ),
    );

    // Add listener to debug animation progress
    _successAnimation.addListener(() {});

    // Failure animation
    _failureAnimationController = AnimationController(
      duration: const Duration(milliseconds: 800),
      vsync: this,
    );
    _failureAnimation = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(
        parent: _failureAnimationController,
        curve: Curves.bounceOut,
      ),
    );
  }

  // Get current location for the map
  void _getCurrentLocation() async {
    try {
      LocationPermission permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }

      if (permission == LocationPermission.whileInUse ||
          permission == LocationPermission.always) {
        Position position = await Geolocator.getCurrentPosition();
        if (mounted) {
          setState(() {
            _currentPosition = position;
          });
        }
      }
    } catch (e) {
      debugPrint('Error getting location: $e');
    }
  }

  // Start recognition process with animations
  void _startRecognition() async {

    setState(() {
      _recognitionState = RecognitionState.scanning;
      _currentMarkdownContent = """
      """;
    });

    // Start pulse animation
    _pulseAnimationController.repeat(reverse: true);

    // await WidgetsBinding.instance.endOfFrame;
    // await Future.delayed(const Duration(milliseconds: 50));

    // // --- TEST CODE: BYPASS INFERENCE ---
    // // Simula un ritardo di scansione
    // await Future.delayed(const Duration(seconds: 2));

    // // Usa il primo waypoint disponibile o un ID di default
    // int waypointId = _waypoints.isNotEmpty ? _waypoints.first.id : 1;

    // // Simula la disponibilità di tutte le risorse
    // Map<String, dynamic> availableResources = {
    //   "readme": 1,
    //   "links": 1,
    //   "images": 1,
    //   "video": 1,
    //   "pdf": 1,
    //   "audio": 1,
    // };

    // _handleRecognitionSuccess(waypointId, availableResources, widget.isOffline);
    // return;
    // // -----------------------------------

    try {
      Uint8List? bytes;
      int sensorOrientation = 0;

      final XFile file = await _cameraController!.takePicture();
      bytes = await file.readAsBytes();
      sensorOrientation = _cameraController!.description.sensorOrientation;

      int waypointId = -1;
      Map<String, dynamic> availableResources = {};

      if (widget.isOffline) {
        debugPrint("OFFLINE RECOGNITION");
        if(_offlineRecognitionService == null) {
          throw Exception("Offline Recognition Service not initialized");
        }
        // final rotatedBytes = Uint8List.fromList(img.encodeJpg(capturedImage));
        final int orientation = _cameraController!.description.sensorOrientation;
        final rotatedBytes = await compute(_processImageInIsolate, {
          'bytes': bytes,
          'orientation': orientation,
        });

        // waypointId = await _offlineRecognitionService!.matchFromImageBytes(rotatedBytes, sensorOrientation: 0);

        waypointId = await _offlineRecognitionService!.matchFromImageBytes(
          rotatedBytes,
          sensorOrientation: 0,
          useGeometry: false,
          queryLat: _currentPosition?.latitude,
          queryLon: _currentPosition?.longitude,
          queryAccuracyM: _currentPosition?.accuracy,
        );

        if (waypointId != -1) {
          availableResources = {
            "readme": 0,
            "links": 0,
            "images": 0,
            "video": 0,
            "pdf": 0,
            "audio": 0,
          };
          final images = _offlineImagesByWaypoint[waypointId] ?? [];
          if (images.isNotEmpty) {
            availableResources["images"] = 1;
          }
          final resources = _offlineResourcesByWaypoint[waypointId] ?? {};
          resources.forEach((key, value) {
            if (value is String && value.isNotEmpty) {
              availableResources[key] = 1;
            }
          });

          }
      } else {
        final rotatedBytes = await compute(_processImageInIsolate, {
          'bytes': bytes,
          'orientation': _cameraController!.description.sensorOrientation,
        });

        final result = await _apiService.inference(
          rotatedBytes,
          widget.tourId,
          _currentPosition?.latitude,
          _currentPosition?.longitude,
          _currentPosition?.accuracy,
          baseUrl: _apiService.getCurrentBaseUrl(),
        );

        waypointId = result.data["result"] ?? -1;
        availableResources = result.data["available_resources"] ?? {};
        debugPrint("AVAILABLE RESOURCES: $availableResources");
      }

      _pulseAnimationController.stop();
      
      final success = waypointId != -1;
      if (success) {

        unawaited(_analytics.logEvent(name: 'recognition_success', parameters: {
          'waypoint_id': waypointId,
          'tour_id': widget.tourId,
          'is_offline': widget.isOffline,
        }));

        _handleRecognitionSuccess(waypointId, availableResources, widget.isOffline);
      } else {
        unawaited(_analytics.logEvent(name: 'recognition_failure', parameters: {
          'tour_id': widget.tourId,
          'is_offline': widget.isOffline,
        }));

        _showError(_getRandomRecognitionFailureMessage());
        setState(() {
          _recognitionFailureMessage = _getRandomRecognitionFailureMessage();
          _recognitionState = RecognitionState.failure;
        });        
        _failureAnimationController.forward();
        Timer(const Duration(seconds: 3), () {
          if (mounted) _resetRecognition();
        });
      }
    } catch(e) {
      debugPrint("Error during recognition: $e");
      unawaited(_analytics.logEvent(name: 'recognition_error', parameters: {
        'tour_id': widget.tourId,
        'is_offline': widget.isOffline,
        'error': e,
      }));
      _showError(_getRandomRecognitionFailureMessage());
      setState(() {
        _recognitionFailureMessage = _getRandomRecognitionFailureMessage();
        _recognitionState = RecognitionState.failure;
      });      
      _failureAnimationController.forward();
      Timer(const Duration(seconds: 3), () {
        if (mounted) _resetRecognition();
      });
    }
  }

  // NUOVO: Verifica se il tour è completato
  Future<void> _checkTourCompletion() async {
    try {
      // Ottieni tutti gli ID dei waypoint del tour corrente
      List<int> allWaypointIds =
          _waypoints.where((waypoint) => !waypoint.isPreliminaryInfo).map((waypoint) => waypoint.id).toList();

      // Aggiungi anche gli ID dei sub-waypoint se presenti
      for (var waypoint in _waypoints) {
        if (waypoint.subWaypoints != null) {
          allWaypointIds.addAll(waypoint.subWaypoints!.map((sub) => sub.id));
        }
      }

      debugPrint("All waypoint IDs: $allWaypointIds");

      // Verifica se il tour è completato
      final isCompleted = await _localStateService.checkTourCompletion(
        widget.tourId,
        allWaypointIds,
      );

      if (isCompleted && mounted) {
        _showTourCompletedDialog();
      }
    } catch (e) {
      debugPrint('Error checking tour completion: $e');
    }
  }

  // NUOVO: Mostra dialog di tour completato
  void _showTourCompletedDialog() {
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (BuildContext context) {
        return AlertDialog(
          title: Text('congratulations'.tr()),
          content: Text(
            'tour_completed'.tr(),
          ),
          actions: [
            TextButton(
              onPressed: () {
                Navigator.of(context).pop();
                // Navigator.of(context).pop(); // Torna alla schermata precedente
              },
              child: Text('continue'.tr()),
            ),
          ],
        );
      },
    );
  }

  // Manual AR overlay animation using Timer
  void _startAROverlayAnimation() {
    _arOverlayProgress = 0.0;

    Timer.periodic(const Duration(milliseconds: 50), (timer) {
      if (!mounted || _recognitionState != RecognitionState.success) {
        timer.cancel();
        return;
      }

      setState(() {
        _arOverlayProgress += 0.05; // Increase by 5% every 50ms
      });

      if (_arOverlayProgress >= 1.0) {
        _arOverlayProgress = 1.0;
        timer.cancel();
      }
    });
  }

  // Reset recognition to initial state with animation
  void _resetRecognition() async {
    // Reset manual AR overlay progress
    _arOverlayProgress = 0.0;
    const closingDuration = Duration(milliseconds: 300);

    // Check if we need to exit AR Mode
    bool wasARMode = _isARMode;
    if (wasARMode) {
      setState(() {
        _isARMode = false;
      });

    arSessionManager?.dispose();
    arSessionManager = null;
    arObjectManager = null;
    arAnchorManager = null;
    _totemSpawned = false;
    _totemBaseNode = null;
    _totemBodyNode = null;
    _markdownScrollTimer?.cancel();
    _markdownScrollTimer = null;
    _totemMarkdownCardNode = null;
    _arNodeToResourceType.clear();
    _markdownMaxScrollOffset = 0.0;
    _markdownScrollFrame = 0;
    }


    // Animate out current state
    if (_recognitionState == RecognitionState.success) {
      _successAnimationController.duration = closingDuration;
      await _successAnimationController.reverse();
      _successAnimationController.duration = const Duration(milliseconds: 1200);
    } else if (_recognitionState == RecognitionState.failure) {
      _failureAnimationController.duration = closingDuration;
      await _failureAnimationController.reverse();
      _failureAnimationController.duration = const Duration(milliseconds: 800);
    }

    _sheetController.animateTo(
      _initialSheetSize,
      duration: const Duration(milliseconds: 100),
      curve: Curves.easeInOut,
    );


    setState(() {
      _recognitionState = RecognitionState.ready;
      _recognitionFailureMessage = "";
    });

    _successAnimationController.reset();
    _failureAnimationController.reset();
    _pulseAnimationController.reset();

    if (wasARMode) {
      await Future.delayed(const Duration(milliseconds: 500));
      await _initializeCamera();
    }

  }

  // Navigate back to previous screen
  void _navigateBack(BuildContext context) {
    Navigator.of(context).pop();
  }

  Widget _buildResourceButtonsContent() {
    final List<Map<String, dynamic>> resources =
        _getAvailableIconsData()
            .where((e) => e['isVisible'] == true)
            .map((e) => Map<String, dynamic>.from(e))
            .toList();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          widget.landmarkName,
          style: const TextStyle(
            fontSize: 22,
            fontWeight: FontWeight.bold,
            color: AppColors.textPrimary,
          ),
        ),
        const SizedBox(height: 8),
        const Text(
          'Risorse disponibili',
          style: TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w600,
            color: AppColors.textPrimary,
          ),
        ),
        const SizedBox(height: 16),

        if (resources.isEmpty)
          const Text(
            'Nessuna risorsa disponibile per questo waypoint.',
            style: TextStyle(color: AppColors.textSecondary),
          )
        else
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: [
              for (final resource in resources)
                ElevatedButton.icon(
                  onPressed: () {
                    _updateDraggableSheetContent(
                      resource['type'] as String,
                      _recognizedWaypointId,
                    );
                  },
                  icon: Image.asset(
                    resource['assetPath'] as String,
                    width: 20,
                    height: 20,
                  ),
                  label: Text(resource['label'] as String),
                ),
            ],
          ),
      ],
    );
  }

  List<Map<String, dynamic>> _getAvailableIconsData() {
    return [
      {
        'type': 'text',
        'label': 'Text',
        'assetPath': 'assets/icons/text.png', // Icona 2D
        'modelPath': 'assets/models/AR/buttons/text/b6.gltf', // Modello 3D
        'angle': -pi / 2, // Posizione 2D (Alto)
        'isVisible': _availableResources["readme"] == 1,
      },
      {
        'type': 'link',
        'label': 'Link',
        'assetPath': 'assets/icons/link.png',
        'modelPath': 'assets/models/AR/buttons/link/b5.gltf', // Modello 3D
        'angle': -pi / 4.5, // Posizione 2D (Alto-Destra)
        'isVisible': _availableResources["links"] == 1,
      },
      {
        'type': 'image',
        'label': 'Image',
        'assetPath': 'assets/icons/image.png',
        'modelPath': 'assets/models/AR/buttons/image/b4.gltf', // Modello 3D
        'angle': pi / 4.5, // Posizione 2D (Basso-Destra)
        'isVisible': _availableResources["images"] > 0, // Sempre visibile
      },
      {
        'type': 'video',
        'label': 'Video',
        'assetPath': 'assets/icons/video.png',
        'modelPath': 'assets/models/AR/buttons/video/b1.gltf', // Modello 3D
        'angle': pi / 2, // Posizione 2D (Basso)
        'isVisible': _availableResources["video"] == 1,
      },
      {
        'type': 'document',
        'label': 'Doc',
        'assetPath': 'assets/icons/document.png',
        'modelPath': 'assets/models/AR/buttons/document/b3.gltf', // Modello 3D
        'angle': 2 * pi / 2.5, // Posizione 2D (Basso-Sinistra)
        'isVisible': _availableResources["pdf"] == 1,
      },
      {
        'type': 'audio',
        'label': 'Audio',
        'assetPath': 'assets/icons/audio.png',
        'modelPath': 'assets/models/AR/buttons/audio/b2.gltf', // Modello 3D
        'angle': -2 * pi / 2.5, // Posizione 2D (Alto-Sinistra)
        'isVisible': _availableResources["audio"] == 1,
      },
    ];
  }

  // Build the camera background with live feed
  Widget _buildCameraBackground() {
    if (!_isCameraInitialized || _cameraController == null) {
      return Container(
        width: double.infinity,
        height: double.infinity,
        color: Colors.black,
        child: const Center(
          child: CircularProgressIndicator(color: Colors.white),
        ),
      );
    }

    return SizedBox(
      width: double.infinity,
      height: double.infinity,
      child: GestureDetector(
        onScaleStart: _handleScaleStart,
        onScaleUpdate: _handleScaleUpdate,
        child: CameraPreview(_cameraController!)
      ),
    );
  }

  // Build the central recognition widget with smooth transitions
  Widget _buildCentralRecognitionWidget() {
    return Center(
      child: AnimatedSwitcher(
        duration: const Duration(milliseconds: 600),
        transitionBuilder: (Widget child, Animation<double> animation) {
          return ScaleTransition(
            scale: animation,
            child: FadeTransition(opacity: animation, child: child),
          );
        },
        child: Container(
          key: ValueKey(_recognitionState),
          child: _buildStateWidget(),
        ),
      ),
    );
  }

  // Build the appropriate widget for current state
  Widget _buildStateWidget() {
    switch (_recognitionState) {
      case RecognitionState.ready:
        return _buildReadyState();
      case RecognitionState.scanning:
        return _buildScanningState();
      case RecognitionState.success:
        return _buildSuccessState();
      case RecognitionState.failure:
        return _buildFailureState();
    }
  }

  // Build ready state (blue camera button)
  Widget _buildReadyState() {
    return Center(
      child: GestureDetector(
        onTap: _startRecognition,
        child: Container(
          width: 80,
          height: 80,
          decoration: BoxDecoration(
            color: Colors.blue,
            shape: BoxShape.circle,
            boxShadow: [
              BoxShadow(
                color: Colors.blue.withOpacity(0.3),
                blurRadius: 20,
                spreadRadius: 5,
              ),
            ],
          ),
          child: const Icon(Icons.camera_alt, color: Colors.white, size: 40),
        ),
      ),
    );
  }

  // Build scanning state (pulsing camera button)
  Widget _buildScanningState() {
    return Center(
      child: AnimatedBuilder(
        animation: _pulseAnimation,
        builder: (context, child) {
          return Transform.scale(
            scale: _pulseAnimation.value,
            child: Container(
              width: 80,
              height: 80,
              decoration: BoxDecoration(
                color: Colors.blue,
                shape: BoxShape.circle,
                boxShadow: [
                  BoxShadow(
                    color: Colors.blue.withOpacity(0.5),
                    blurRadius: 30,
                    spreadRadius: 10,
                  ),
                ],
              ),
              child: const Icon(Icons.search, color: Colors.white, size: 40),
            ),
          );
        },
      ),
    );
  }

  // Build success state (green checkmark with animated AR overlays)
  Widget _buildSuccessState() {
    // Get screen dimensions
    final screenWidth = MediaQuery.of(context).size.width;
    final screenHeight = MediaQuery.of(context).size.height;

    // Center of the screen (and thus, the central button)
    final centerX = screenWidth / 2;
    final centerY = screenHeight / 2;

    if (_isARMode) {
      return const SizedBox.shrink();
    }

    final responsive = context.r;
    // Configuration for AR overlay elements
    final double arIconRadius = responsive.consultationIconRadius(); // Radius for the AR icons circle
    final double iconSize = responsive.consultationIconSize(); // Size of the _buildSimpleAROverlay widget

    final iconsData = _getAvailableIconsData();

    return Stack(
      children: [
        // Central success indicator with morphing animation
        Center(
          child: AnimatedBuilder(
            animation: _successAnimation,
            builder: (context, child) {
              return Transform.scale(
                scale: _successAnimation.value,
                child: Container(
                  width: 65,
                  height: 65,
                  decoration: BoxDecoration(
                    color: Color.lerp(
                      Colors.blue,
                      Colors.green,
                      _successAnimation.value,
                    ),
                    shape: BoxShape.circle,
                    boxShadow: [
                      BoxShadow(
                        color: Color.lerp(
                          Colors.blue.withOpacity(0.3),
                          Colors.green.withOpacity(0.3),
                          _successAnimation.value,
                        )!.withOpacity(0.5),
                        blurRadius: 20 + (10 * _successAnimation.value),
                        spreadRadius: 5 + (5 * _successAnimation.value),
                      ),
                    ],
                  ),
                  child: AnimatedSwitcher(
                    duration: const Duration(milliseconds: 300),
                    child: Icon(
                      _successAnimation.value > 0.5
                          ? Icons.check
                          : Icons.search,
                      key: ValueKey(_successAnimation.value > 0.5),
                      color: Colors.white,
                      size: 40,
                    ),
                  ),
                ),
              );
            },
          ),
        ),

        // AR overlay elements positioned around the center
        ...iconsData.map((elementData) {
          final double angle = elementData['angle'];
          final double radiusMultiplier = elementData["label"] == 'Close'
              ? 1.15 // Close icon is closer to the center
              : 1.0; // Other icons are at full radius
          final double x = centerX + arIconRadius * radiusMultiplier * cos(angle);
          final double y = centerY + arIconRadius * radiusMultiplier * sin(angle);

          double delay = 0.0;
          if (elementData['type'] == 'text') delay = 0.0;
          if (elementData['type'] == 'link') delay = 0.1;
          if (elementData['type'] == 'image') delay = 0.2;
          if (elementData['type'] == 'video') delay = 0.3;
          if (elementData['type'] == 'document') delay = 0.4;
          if (elementData['type'] == 'audio') delay = 0.5;

          return Positioned(
            left:
                x - (iconSize / 2), // Adjust for icon's own width to center it
            top:
                y - (iconSize / 2), // Adjust for icon's own height to center it
            child: _buildSimpleAROverlay(
              label: elementData['label'],
              delay: delay,
              isVisible: elementData['isVisible'],
              assetPath: elementData['assetPath'],
              iconSize: iconSize, // Use the same size for all icons
              onTap: () {
                debugPrint('${elementData['label']} Info icon tapped!'); 
                _updateDraggableSheetContent(elementData['type'], _recognizedWaypointId);
              
              }
            ),
          );
        }).toList(),

        Builder(
          builder: (context) {
            final double closeAngle = -2 * pi / 1.01;
            final double closeX = centerX + (arIconRadius) * cos(closeAngle); 
            final double closeY = centerY + (arIconRadius) * sin(closeAngle);

            return Positioned(
              left: closeX - (iconSize / 2),
              top: closeY - (iconSize / 2),
              child: _buildSimpleAROverlay(
                label: "Close",
                delay: 0.2,
                isVisible: true,
                assetPath: "assets/icons/back_icon.png",
                iconSize: iconSize,
                onTap: () {
                  debugPrint("Close icon Tapped!");
                  _resetRecognition();
                },
              ),
            );         
          }
        )
      ],
    );
  }

  Widget _buildSimpleAROverlay({
    required String label, // Label for the AR overlay
    required double delay,
    required String assetPath, // Path to your custom icon in the assets folder
    required bool isVisible, // Controls if the overlay is shown
    VoidCallback? onTap, // Callback for tap events
    double iconSize = 50.0, // Size of the icon (width and height)
  }) {
    // If not visible, return an empty widget
    if (!isVisible) {
      return const SizedBox.shrink();
    }

    if (label == 'Close') {
      // Special case for the close icon
      iconSize = iconSize - 15.0;
      }

    // Animation logic based on _arOverlayProgress (from your state) and individual delay
    // Ensure _arOverlayProgress is accessible here, typically from your State class
    double opacity = _arOverlayProgress >= delay ? 1.0 : 0.0;
    double scale = _arOverlayProgress >= delay ? 1.0 : 0.0;

    return Transform.scale(
      scale: scale,
      child: Opacity(
        opacity: opacity,
        child: GestureDetector(
          onTap: onTap,
          behavior:
              HitTestBehavior
                  .opaque, // Ensures the tap area is consistent even if the image has transparency
          child: Image.asset(
            assetPath,
            width: iconSize,
            height: iconSize,
            fit: BoxFit.contain, // Adjust BoxFit as needed
            // Optional: Add an error builder in case the asset fails to load
            errorBuilder: (context, error, stackTrace) {
              debugPrint('Error loading asset: $assetPath, $error');
              return Icon(
                Icons.broken_image, // Placeholder for broken image
                size: iconSize,
                color: Colors.red, // Or any color you prefer for the error icon
              );
            },
          ),
        ),
      ),
    );
  }

  // Build failure state (red prohibition symbol with shake animation)
  Widget _buildFailureState() {
    return Center(
      child: AnimatedBuilder(
        animation: _failureAnimation,
        builder: (context, child) {
          // Add shake effect
          double shake = 0;
          if (_failureAnimation.value > 0.1 && _failureAnimation.value < 0.9) {
            shake =
                (sin(_failureAnimation.value * 20) * 3) *
                (1 - _failureAnimation.value); // Diminishing shake
          }

          return Transform.translate(
            offset: Offset(shake, 0),
            child: Transform.scale(
              scale: _failureAnimation.value,
              child: Container(
                width: 80,
                height: 80,
                decoration: BoxDecoration(
                  color: Color.lerp(
                    Colors.blue,
                    Colors.red,
                    _failureAnimation.value,
                  ),
                  shape: BoxShape.circle,
                  boxShadow: [
                    BoxShadow(
                      color: Color.lerp(
                        Colors.blue.withOpacity(0.3),
                        Colors.red.withOpacity(0.3),
                        _failureAnimation.value,
                      )!.withOpacity(0.5),
                      blurRadius: 20 + (10 * _failureAnimation.value),
                      spreadRadius: 5 + (5 * _failureAnimation.value),
                    ),
                  ],
                ),
                child: AnimatedSwitcher(
                  duration: const Duration(milliseconds: 300),
                  child: Icon(
                    _failureAnimation.value > 0.5 ? Icons.block : Icons.search,
                    key: ValueKey(_failureAnimation.value > 0.5),
                    color: Colors.white,
                    size: 40,
                  ),
                ),
              ),
            ),
          );
        },
      ),
    );
  }

  // Build the back button in top left
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
          onPressed: () => _navigateBack(context),
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

  // Build the mini map in top right using flutter_map
Widget _buildMiniMap(BuildContext context) {
    final screenWidth = MediaQuery.of(context).size.width;
    final mapSize = screenWidth * 0.35;

    return Positioned(
      top: MediaQuery.of(context).padding.top + context.r.space(25),
      right: 16,
      child: Container(
        width: mapSize,
        height: mapSize * 0.7,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(12),
          boxShadow: [
            BoxShadow(
              color: AppColors.cardShadow,
              blurRadius: 8,
              offset: const Offset(0, 2),
            ),
          ],
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(12),
          child:
              _isLoadingWaypoints
                  ? Container(
                    color: Colors.grey[300],
                    child: const Center(
                      child: CircularProgressIndicator(
                        color: AppColors.primary,
                        strokeWidth: 2,
                      ),
                    ),
                  )
                  : _buildMapContent(context),
        ),
      ),
    );
  }

  Widget _buildMapContent(BuildContext context) {
    // Ora che i waypoint sono caricati, calcola quelli vicini
    List<Waypoint> nearbyWaypoints = [];

    if (_currentPosition != null && _waypoints.isNotEmpty) {
      // Calcola le distanze per tutti i waypoint
      List<Map<String, dynamic>> waypointsWithDistance =
          _waypoints.map((waypoint) {
            final distance =
                Geolocator.distanceBetween(
                  _currentPosition!.latitude,
                  _currentPosition!.longitude,
                  waypoint.latitude,
                  waypoint.longitude,
                ) /
                1000; // Converti da metri a km

            return {'waypoint': waypoint, 'distance': distance};
          }).toList();

      // Ordina per distanza (dal più vicino al più lontano)
      waypointsWithDistance.sort(
        (a, b) => a['distance'].compareTo(b['distance']),
      );

      // Prendi solo i primi 5 waypoint più vicini
      nearbyWaypoints =
          waypointsWithDistance
              .take(5)
              .map((item) => item['waypoint'] as Waypoint)
              .toList();
    } else if (_waypoints.isNotEmpty) {
      // Se non hai posizione corrente, mostra i primi 5 waypoint
      nearbyWaypoints = _waypoints.take(5).toList();
    }

    // Calcola il centro della mappa
    LatLng mapCenter;
    if (_currentPosition != null) {
      mapCenter = LatLng(
        _currentPosition!.latitude,
        _currentPosition!.longitude,
      );
    } else if (nearbyWaypoints.isNotEmpty) {
      // Calcola il centro medio dei waypoint
      double avgLat =
          nearbyWaypoints.map((w) => w.latitude).reduce((a, b) => a + b) /
          nearbyWaypoints.length;
      double avgLng =
          nearbyWaypoints.map((w) => w.longitude).reduce((a, b) => a + b) /
          nearbyWaypoints.length;
      mapCenter = LatLng(avgLat, avgLng);
    } else {
      // Fallback: usa le coordinate del landmark originale
      mapCenter = LatLng(widget.latitude, widget.longitude);
    }

    // List<LatLng> pointsForBounds = _waypoints
    //     .map((w) => LatLng(w.latitude, w.longitude))
    //     .toList();

    //   if (_currentPosition != null) {
    //     pointsForBounds.add(
    //       LatLng(_currentPosition!.latitude, _currentPosition!.longitude),
    //     );
    //   }

    //   if (pointsForBounds.isEmpty) {
    //     pointsForBounds.add(LatLng(widget.latitude, widget.longitude));
    //   }

    //   final bounds = LatLngBounds.fromPoints(pointsForBounds);

    return FlutterMap(
      mapController: _mapController,
      options: MapOptions(
        initialCenter: mapCenter,
        initialZoom: 12.0,
        interactionOptions: const InteractionOptions(
          flags: InteractiveFlag.none,
        ),
      ),
      children: [
        // Base map layer
        _baseMapLayer(),
        // TileLayer(
        //   urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
        //   userAgentPackageName: 'com.picaresque.xrtourguide',
        // ),

        // Current location marker (se disponibile)
        if (_currentPosition != null)
          CurrentLocationLayer(
            style: LocationMarkerStyle(
              marker: Container(
                decoration: BoxDecoration(
                  color: AppColors.primary.withOpacity(0.6),
                  shape: BoxShape.circle,
                ),
                padding: const EdgeInsets.all(4),
                child: const Center(
                  child: Icon(
                    Icons.person_pin_circle,
                    color: Colors.white,
                    size: 12,
                  ),
                ),
              ),
              markerSize: const Size.square(24),
              accuracyCircleColor: AppColors.primary.withOpacity(0.2),
              headingSectorColor: AppColors.primary.withOpacity(0.6),
            ),
          ),

        // Waypoint markers (solo se ci sono waypoint caricati)
        if (nearbyWaypoints.isNotEmpty)
          MarkerLayer(
            markers:
                nearbyWaypoints.asMap().entries.map((entry) {
                  final index = entry.key;
                  final waypoint = entry.value;

                  return Marker(
                    point: LatLng(waypoint.latitude, waypoint.longitude),
                    width: 28,
                    height: 28,
                    child: Container(
                      decoration: BoxDecoration(
                        color: Colors.blue.withOpacity(0.8),
                        shape: BoxShape.circle,
                        border: Border.all(color: Colors.white, width: 2),
                        boxShadow: [
                          BoxShadow(
                            color: Colors.black.withOpacity(0.3),
                            blurRadius: 3,
                            offset: const Offset(0, 1),
                          ),
                        ],
                      ),
                      child: Center(
                        child: Text(
                          '${index + 1}',
                          style: TextStyle(
                            color: Colors.white,
                            fontWeight: FontWeight.bold,
                            fontSize: context.r.sp(10),
                          ),
                        ),
                      ),
                    ),
                  );
                }).toList(),
          ),
      ],
    );
  }

  // Build the draggable bottom sheet with landmark information
  Widget _buildDraggableSheet(BuildContext context) {
    return DraggableScrollableSheet(
      key: const ValueKey("DraggableSheet"),
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
              // Drag handle
              Container(
                margin: const EdgeInsets.only(top: 12, bottom: 8),
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                  color: AppColors.divider,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
              // Scrollable content
              Expanded(
                child:
                    _currentActiveContent != null
                        ? SingleChildScrollView(
                          controller: scrollController,
                          padding: const EdgeInsets.symmetric(
                            horizontal: 20,
                            vertical: 10,
                          ), // Adjust padding
                          child: _currentActiveContent!,
                        )
                        : Center(
                          child: Text(
                            'Select content type.',
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

  @override
  Widget build(BuildContext context) {
    // Define the size for the static semi-transparent circle
    // It should be large enough to encompass the largest state of the central button (e.g., ready state button size 80)
    final double staticOuterCircleSize = context.r.consultationOuterCircleSize(); // Example size, adjust as needed

    final screenWidth = MediaQuery.of(context).size.width;
    final mapSize = screenWidth * 0.35;
    final miniMapHeight = mapSize * 0.7;


    return Scaffold(
      backgroundColor: widget.enableRecognition ? Colors.black : Colors.white, // Black background for camera feel
      extendBodyBehindAppBar: true,
      body: Stack(
        children: [
          // Live camera background
          if (_isARMode) 
            ARView(
              onARViewCreated: onARViewCreated,
              planeDetectionConfig: PlaneDetectionConfig.horizontal,
              )
          else if (widget.enableRecognition)
            _buildCameraBackground()
          else
            Container(color: Colors.white, width: double.infinity, height: double.infinity),

          // --- Static Semi-transparent Circle (added here) ---
          if (!_isARMode)
            Center(
              // Use Center to position it in the middle of the screen
              child: Container(
                width: staticOuterCircleSize,
                height: staticOuterCircleSize,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  border: Border.all(
                    color: Colors.black.withOpacity(0.2), // Subtle border
                    width: 4,
                  ),
                ),
              ),
            ),
          // --- End Static Semi-transparent Circle ---

          // Central recognition widget overlay (will be on top of the static circle)
          if (!(_isARMode && _recognitionState == RecognitionState.success))
            _buildCentralRecognitionWidget(),

          // Back button (top left)
          _buildBackButton(context),

          // Mini map (top right)
          if(widget.enableRecognition) _buildMiniMap(context),

          // Draggable bottom sheet with landmark info
          _buildDraggableSheet(context),

          if (_recognitionState == RecognitionState.success && widget.enableRecognition)
            Positioned(
              top: MediaQuery.of(context).padding.top + context.r.space(16) + miniMapHeight + context.r.space(10),
              right: 16,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                decoration: BoxDecoration(
                  color: Colors.black45,
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: Colors.white24),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.camera_alt, color: Colors.white, size: 16),
                    const SizedBox(width: 8),
                    Switch(
                      value: _isARMode,
                      activeColor: AppColors.primary,
                      activeTrackColor: AppColors.primary.withOpacity(0.5),
                      inactiveThumbColor: Colors.grey,
                      inactiveTrackColor: Colors.grey.withOpacity(0.5),
                      onChanged: (val) {
                        _toggleARMode();
                      },
                    ),
                    const SizedBox(width: 8),
                    const Icon(Icons.view_in_ar, color: Colors.white, size: 16)
                  ],
                ),
              ),
            ),

          if (_isARMode && _recognitionState == RecognitionState.success && !_totemSpawned)
            Positioned(
              bottom: MediaQuery.of(context).size.height * 0.15,
              left: 20,
              right: 20,
              child: Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: Colors.black87,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(
                  "Punto Riconosciuto! \n Tocca il pavimento per posizionare il Totem",
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Colors.white, fontSize: context.r.sp(16)),
                )
              )
            )

        ],
      ),
    );
  }
}

// Full-screen image viewer widget (kept as it was part of the original code,
// but not directly used by _updateDraggableSheetContent for 'image' type now)
class _FullScreenImageViewer extends StatefulWidget {
  final List<String> images;
  final int initialIndex;

  const _FullScreenImageViewer({
    required this.images,
    required this.initialIndex,
  });

  @override
  State<_FullScreenImageViewer> createState() => _FullScreenImageViewerState();
}

class _FullScreenImageViewerState extends State<_FullScreenImageViewer> {
  late PageController _pageController;
  late int _currentIndex;

  @override
  void initState() {
    super.initState();
    _currentIndex = widget.initialIndex;
    _pageController = PageController(initialPage: widget.initialIndex);
  }

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.close, color: Colors.white),
          onPressed: () => Navigator.of(context).pop(),
        ),
        title: Text(
          '${_currentIndex + 1} of ${widget.images.length}',
          style: const TextStyle(color: Colors.white),
        ),
        centerTitle: true,
      ),
      body: PageView.builder(
        controller: _pageController,
        onPageChanged: (index) {
          setState(() {
            _currentIndex = index;
          });
        },
        itemCount: widget.images.length,
        itemBuilder: (context, index) {
          return Center(
            child: InteractiveViewer(
              child: Image.network(
                widget.images[index],
                fit: BoxFit.contain,
                loadingBuilder: (context, child, loadingProgress) {
                  if (loadingProgress == null) return child;
                  return const Center(
                    child: CircularProgressIndicator(color: Colors.white),
                  );
                },
                errorBuilder: (context, error, stackTrace) {
                  return const Center(
                    child: Icon(
                      Icons.image_not_supported,
                      color: Colors.white,
                      size: 60,
                    ),
                  );
                },
              ),
            ),
          );
        },
      ),
    );
  }
}
