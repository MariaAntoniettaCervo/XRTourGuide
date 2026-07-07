// lib/screens/tour_detail_screen.dart

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:geolocator/geolocator.dart';
import 'package:flutter_map_location_marker/flutter_map_location_marker.dart';
import 'package:xr_tour_guide/services/auth_service.dart';
import 'models/app_colors.dart';
import "models/waypoint.dart";
import 'models/review.dart';
import 'models/tour.dart';
import 'services/tour_service.dart';
import 'services/api_service.dart';
import 'camera_screen.dart';
import 'package:url_launcher/url_launcher.dart';
import 'review_list.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import "package:easy_localization/easy_localization.dart";
import 'services/local_state_service.dart';
import 'services/offline_tour_service.dart';
import "dart:io";
import "package:path_provider/path_provider.dart";
import 'package:flutter_map_pmtiles/flutter_map_pmtiles.dart';
import 'elements/zlib_image.dart';
import 'services/analytics_service.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'consultation_screen.dart';
import 'utils/responsive.dart';
import 'utils/platform_page_route.dart';

class TourDetailScreen extends ConsumerStatefulWidget {
  final int tourId;
  final bool isGuest;
  final bool isOffline;

  const TourDetailScreen({
    Key? key,
    required this.tourId,
    required this.isGuest,
    this.isOffline = false,
  }) : super(key: key);

  @override
  ConsumerState<TourDetailScreen> createState() => _TourDetailScreenState();
}

class _TourDetailScreenState extends ConsumerState<TourDetailScreen>
    with TickerProviderStateMixin {
  late TourService _tourService;
  late ApiService _apiService;
  late LocalStateService _localStateService;
  late OfflineStorageService _offlineService;
  late AnalyticsService _analytics;
  Set<int> _scannedWaypoints = {};

  Map<int, List<String>> _offlineImagesByWaypoint = {};
  String? _offlineTourImagePath;

  String _selectedTab = 'About';
  late List<bool> _expandedWaypoints;
  Map<int, List<bool>> _expandedSubWaypoints = {};
  int _currentImageIndex = 0;
  late PageController _pageController;
  final MapController _mapController = MapController();

  // Selected waypoint for the itinerary view
  int _selectedWaypointIndex = 0;
  int _selectedWaypointIndexMappa = 0;

  // Animation controllers
  late AnimationController _mapAnimationController;
  late Animation<double> _mapAnimation;

  // Bottom sheet controller for itinerary view
  late DraggableScrollableController _sheetController;
  double _sheetMinSize = 0.15; // Initial height ratio
  double _sheetMaxSize =
      0.4; // Maximum height ratio (This will be adjusted in the Itinerario view)

  Tour? _tourDetails;
  bool _isLoadingTourDetails = true;

  // Define your waypoints with coordinates
  List<Waypoint> _waypoints = [];
  List<Waypoint> get _realWaypoints => _waypoints.where((wp) => !wp.isPreliminaryInfo).toList();
  List<Waypoint> get _preliminaryWaypoints => _waypoints.where((wp) => wp.isPreliminaryInfo).toList();
  bool get _hasMapWaypoints => _realWaypoints.isNotEmpty;
  
  bool _isLoadingWaypoints = true;

  List<Review> _reviews = [];
  bool _isLoadingReviews = true;
  bool _hasUserAlreadyReviewed = false;
  bool _isCheckingUserReview = false;

  double _userRating = 0.0;
  final TextEditingController _reviewController = TextEditingController();

  late LocationPermission _permission;
  Position? _currentPosition;

  bool _isDownloading = false;
  bool _isAvailableOffline = false;
  final bool isOffline = false;

  String? _pmtilesPath;
  late Future<PmTilesTileProvider> _futureTileProvider;

  List<String> _getWaypointImagesFor(Waypoint wp) {
    return widget.isOffline
        ? (_offlineImagesByWaypoint[wp.id] ?? [])
        : wp.images;
  }

  @override
  void initState() {
    super.initState();
    debugPrint(
      'TOUR initState: tourId=${widget.tourId}, isOffline=${widget.isOffline}',
    );
    try {
      _apiService = ref.read(apiServiceProvider);
      debugPrint('TOUR apiService OK');
    } catch (e) {
      debugPrint('TOUR apiService ERROR: $e');
    }
    _tourService = ref.read(tourServiceProvider);
    _apiService = ref.read(apiServiceProvider);
    _localStateService = ref.read(localStateServiceProvider);
    _offlineService = ref.read(offlineStorageServiceProvider);
    _analytics = ref.read(analyticsServiceProvider);
    if (widget.isOffline) {
      debugPrint("OFFLINE TOUR");
      _initOfflineMap();
      _loadOfflineData();
    } else {
      debugPrint("ONLINE TOUR");
      _loadData();
      // _incrementViewCount();
    }
    if (!widget.isOffline && !widget.isGuest) {
      _checkUserReviewStatusNonBlocking();
    }
    _checkLocationPermission();
    _loadScannedWaypoints();
    _checkOfflineAvailability();
    _pageController = PageController();

    // Initialize animation controllers
    _mapAnimationController = AnimationController(
      duration: const Duration(milliseconds: 500),
      vsync: this,
    );

    _mapAnimation = CurvedAnimation(
      parent: _mapAnimationController,
      curve: Curves.easeInOut,
    );

    // Initialize bottom sheet controller
    _sheetController = DraggableScrollableController();
  }

  Future<void> _loadData() async {
    // Load all data in parallel
    await Future.wait([_loadTourDetails(), _loadWaypoints(), _loadReviews()]);
  }

  Future<void> _checkUserReviewStatusNonBlocking() async {
    setState(() => _isCheckingUserReview = true);
    try {
      final hasReviewed = await _tourService.hasUserReviewedTour(widget.tourId);
      if (!mounted) return;
      setState(() {
        _hasUserAlreadyReviewed = hasReviewed;
        _isCheckingUserReview = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _isCheckingUserReview = false);
    }
  }

  Future<void> _initOfflineMap() async {
    final dir = await getApplicationDocumentsDirectory();
    final path =
        '${dir.path}/offline_tours_data/tour_${widget.tourId}/tour_${widget.tourId}.pmtiles';
    if (await File(path).exists()) {
      debugPrint("PMTiles file found at $path");
      setState(() {
        _pmtilesPath = path;
        _futureTileProvider = PmTilesTileProvider.fromSource(_pmtilesPath!);
      });
    } else {
      debugPrint("PMTiles file not found at $path");
    }
  }

  Widget _baseMapLayer() {
    if (widget.isOffline && _pmtilesPath != null) {
      return FutureBuilder<PmTilesTileProvider>(
        future: _futureTileProvider,
        builder: (context, snapshot) {
          if (snapshot.hasData) {
            return TileLayer(tileProvider: snapshot.data!, urlTemplate: '');
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

  Future<void> _loadOfflineData() async {
    if (!widget.isOffline) return;

    try {
      final offlineData = await _offlineService.getOfflineTourData(
        widget.tourId,
      );
      if (offlineData != null) {
        final appDir = await getApplicationDocumentsDirectory();
        _offlineTourImagePath =
            "${appDir.path}/offline_tours_data/tour_${widget.tourId}/default_image.jpg";

        final Map<int, List<String>> imagesByWp = {};
        final List wps = (offlineData['waypoints'] as List?) ?? [];
        for (final wp in wps) {
          final id = (wp['id'] as num).toInt();
          final localImages =
              (wp['local_images'] as List?)?.cast<String>() ?? <String>[];
          imagesByWp[id] = localImages;
        }
        final List subTours = (offlineData['sub_tours'] as List?) ?? [];
        debugPrint("SUbtours: ${subTours}");
        for (final st in subTours) {
          final List subWp = (st['waypoints'] as List?) ?? [];
          for (final wp in subWp) {
            final id = (wp['id'] as num).toInt();
            final localImages =
                (wp['local_images'] as List?)?.cast<String>() ?? <String>[];
            imagesByWp[id] = localImages;
          }
        }

        final List<Waypoint> mainWaypoints =
            wps
                .map<Waypoint>(
                  (wp) => Waypoint.fromJson(wp as Map<String, dynamic>),
                )
                .toList();
        mainWaypoints.sort(Waypoint.compareByPosition);

        final List<Waypoint> subTourWaypoints = <Waypoint>[];
        for (final st in subTours) {
          final subTourInfo = st['sub_tour'] as Map<String, dynamic>?;
          if (subTourInfo == null) continue;

          final subWpJson = (st['waypoints'] as List?) ?? [];
          final subWps =
              subWpJson
                  .map<Waypoint>(
                    (wp) => Waypoint.fromJson(wp as Map<String, dynamic>),
                  )
                  .toList();
          subWps.sort(Waypoint.compareByPosition);

          final subTourWaypoint = Waypoint(
            id: (subTourInfo['id'] as num).toInt(),
            title: (subTourInfo['title'] ?? '') as String,
            subtitle: (subTourInfo['description'] ?? '') as String,
            description: (subTourInfo['description'] ?? '') as String,
            latitude: (subTourInfo['lat'] as num?)?.toDouble() ?? 0.0,
            longitude: (subTourInfo['lon'] as num?)?.toDouble() ?? 0.0,
            images: const [], // il contenitore non ha immagini proprie
            category: (subTourInfo['category'] ?? 'INDOOR') as String,
            position: (subTourInfo["position"] as num?)?.toInt() ?? 999999,
            subWaypoints: subWps,
          );
          subTourWaypoints.add(subTourWaypoint);
        }

        if (mounted) {
          setState(() {
            _offlineImagesByWaypoint = imagesByWp;
            _tourDetails = Tour.fromJson(offlineData['tour']);
            final mergedWaypoints = [...mainWaypoints, ...subTourWaypoints]
              ..sort(Waypoint.compareByPosition);
            _waypoints = mergedWaypoints;
            _expandedWaypoints = List.generate(
              _waypoints.length,
              (i) => i == 0,
            );
            _expandedSubWaypoints.clear();
            for (int i = 0; i < _waypoints.length; i++) {
              if (_waypoints[i].subWaypoints != null &&
                  _waypoints[i].subWaypoints!.isNotEmpty) {
                _expandedSubWaypoints[i] = List.generate(
                  _waypoints[i].subWaypoints!.length,
                  (subIndex) =>
                      false, // Tutti i sub-waypoints inizialmente chiusi
                );
              }
            }

            _isLoadingTourDetails = false;
            _isLoadingWaypoints = false;
            _isLoadingReviews =
                false; // Assuming reviews are not stored offline
          });
        }
      }
    } catch (e) {
      debugPrint("Error loading offline data: $e");
      if (mounted) {
        setState(() {
          _isLoadingTourDetails = false;
          _isLoadingWaypoints = false;
          _isLoadingReviews = false;
        });
      }
    }
  }

  Widget _offlineImagePlaceholder() {
    return Container(
      width: 80,
      height: 80,
      decoration: BoxDecoration(
        color: Colors.grey.shade300,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Icon(
        Icons.image_not_supported,
        color: Colors.grey.shade600,
        size: 30,
      ),
    );
  }

  Future<void> _checkOfflineAvailability() async {
    final isOffline = await _offlineService.isTourAvailableOffline(
      widget.tourId,
    );
    if (mounted) {
      setState(() {
        _isAvailableOffline = isOffline;
      });
    }
  }

  Future<void> _downloadTourOffline() async {
    unawaited(
      _analytics.logEvent(
        name: 'download_tour_offline',
        parameters: {'tour_id': widget.tourId},
      ),
    );
    setState(() => _isDownloading = true);

    try {
      final success = await _offlineService.downloadTourOffline(widget.tourId);

      if (mounted) {
        setState(() {
          _isDownloading = false;
          _isAvailableOffline = success;
        });

        if (success) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('tour_downloaded_success'.tr()),
              backgroundColor: Colors.green,
            ),
          );
        } else {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('tour_download_failed'.tr()),
              backgroundColor: Colors.red,
            ),
          );
        }
      }
    } catch (e) {
      if (mounted) {
        setState(() => _isDownloading = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('tour_download_failed'.tr()),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }

  Future<void> _confirmRemoveOfflineTour() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder:
          (context) => AlertDialog(
            title: Text("remove_offline_tour".tr()),
            content: Text("confirm_remove_offline_tour".tr()),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(context).pop(false),
                child: Text("cancel".tr()),
              ),
              TextButton(
                onPressed: () => Navigator.of(context).pop(true),
                child: Text(
                  "remove".tr(),
                  style: const TextStyle(color: Colors.red),
                ),
              ),
            ],
          ),
    );

    if (confirmed == true) {
      await _removeOfflineTour();
      unawaited(
        _analytics.logEvent(
          name: 'remove_offline_tour',
          parameters: {'tour_id': widget.tourId},
        ),
      );
    }
  }

  Future<void> _removeOfflineTour() async {
    setState(() => _isDownloading = true);
    try {
      final success = await _offlineService.removeTourOffline(widget.tourId);
      if (mounted) {
        setState(() {
          _isDownloading = false;
          if (success) _isAvailableOffline = false;
        });
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              success
                  ? 'tour_removed_success'.tr()
                  : 'tour_removed_failed'.tr(),
            ),
            backgroundColor: success ? Colors.green : Colors.red,
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        setState(() => _isDownloading = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('tour_removed_failed'.tr()),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }

  Future<void> _incrementViewCount() async {
    try {
      await _apiService.incrementTourViews(
        widget.tourId,
        baseUrl: _apiService.getCurrentBaseUrl(),
      );
    } catch (e) {
      debugPrint('Error incrementing view count: $e');
    }
  }

  Future<void> _loadScannedWaypoints() async {
    try {
      final scannedIds = await _localStateService.getScannedWaypoints(
        widget.tourId,
      );
      if (mounted) {
        setState(() {
          _scannedWaypoints = scannedIds.toSet();
        });
      }
    } catch (e) {
      debugPrint('Error loading scanned waypoints: $e');
    }
  }

  Future<void> _loadTourDetails() async {
    try {
      final tour = await _tourService.getTourById(widget.tourId);
      if (mounted) {
        setState(() {
          _tourDetails = tour;
          _isLoadingTourDetails = false;
          debugPrint("STATUS: " + _tourDetails!.status);
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _isLoadingTourDetails = false;
        });
        _showError('error_loading_tour'.tr());
      }
    }
  }

  Future<void> _loadWaypoints() async {
    try {
      final waypoints = await _tourService.getWaypointsByTour(widget.tourId);
      if (mounted) {
        setState(() {
          _waypoints = waypoints;
          _isLoadingWaypoints = false;

          // Inizializza _expandedWaypoints solo per i waypoints principali
          _expandedWaypoints = List.generate(
            _waypoints.length,
            (index) => index == 0,
          );

          // Inizializza _expandedSubWaypoints per ogni waypoint che ha sub-waypoints
          _expandedSubWaypoints.clear();
          for (int i = 0; i < _waypoints.length; i++) {
            if (_waypoints[i].subWaypoints != null &&
                _waypoints[i].subWaypoints!.isNotEmpty) {
              _expandedSubWaypoints[i] = List.generate(
                _waypoints[i].subWaypoints!.length,
                (subIndex) =>
                    false, // Tutti i sub-waypoints inizialmente chiusi
              );
            }
          }
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _isLoadingWaypoints = false;
          _waypoints = [];
          _expandedWaypoints = [];
          _expandedSubWaypoints.clear();
        });
        _showError('error_loading_waypoints'.tr());
      }
    }
  }

  Future<void> _loadReviews() async {
    try {
      final reviews = await _tourService.getReviewByTour(
        tourId: widget.tourId,
        userId: 0, // Assuming 0 for guest users, adjust as needed
        max: 3,
      );
      if (mounted) {
        setState(() {
          _reviews = reviews;
          _isLoadingReviews = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _isLoadingReviews = false;
        });
        _showError('error_loading_reviews'.tr());
      }
    }
  }

  void _showError(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), backgroundColor: Colors.red),
    );
  }

  @override
  void dispose() {
    _pageController.dispose();
    _mapAnimationController.dispose();
    _sheetController.dispose();
    super.dispose();
  }

  Future<void> _checkLocationPermission() async {
    _permission = await Geolocator.checkPermission();
    if (_permission == LocationPermission.denied) {
      _permission = await Geolocator.requestPermission();
      if (_permission == LocationPermission.denied) {
        debugPrint('Location permissions are denied.');
        return;
      }
    }

    if (_permission == LocationPermission.deniedForever) {
      debugPrint(
        'Location permissions are permanently denied. Please enable them in settings.',
      );
      return;
    }

    _getCurrentLocation();
  }

  void _getCurrentLocation() {
    Geolocator.getPositionStream().listen((Position position) {
      if (mounted) {
        setState(() {
          _currentPosition = position;
        });
      }
    });
  }

  // Method to launch map application
  Future<void> _launchMapApp(double latitude, double longitude) async {
    unawaited(
      _analytics.logEvent(
        name: 'launch_map_app',
        parameters: {
          'latitude': latitude,
          'longitude': longitude,
          'source': 'itinerary_view',
        },
      ),
    );
    final String googleMapsUrl =
        'https://www.google.com/maps/dir/?api=1&destination=$latitude,$longitude&travelmode=driving';
    final String appleMapsUrl =
        'http://maps.apple.com/?daddr=$latitude,$longitude';

    if (Theme.of(context).platform == TargetPlatform.iOS) {
      if (await canLaunchUrl(Uri.parse(appleMapsUrl))) {
        await launchUrl(Uri.parse(appleMapsUrl));
      } else {
        _showError('error_launching_maps'.tr());
      }
    } else {
      if (await canLaunchUrl(Uri.parse(googleMapsUrl))) {
        await launchUrl(Uri.parse(googleMapsUrl));
      } else {
        _showError('error_launching_maps'.tr());
      }
    }
  }

  void _centerMap(LatLng latLng) {
    _mapController.move(latLng, _mapController.camera.zoom);
  }

  // Method to build a waypoint marker for the map view
  Marker _buildWaypointMarker(
    int index,
    Waypoint waypoint, {
    bool isItineraryView = false,
  }) {
    final bool isSelected = isItineraryView ? false : _selectedWaypointIndex == index ;
    final bool isSelectedMappa =
        _selectedWaypointIndexMappa == index && !isItineraryView;

    return Marker(
      point: LatLng(waypoint.latitude, waypoint.longitude),
      width: 60, // Increased size for better tapping
      height: 60, // Increased size for better tapping
      child: GestureDetector(
        onTap: () {
          debugPrint('Tapped on Waypoint ${index + 1}');
          _centerMap(LatLng(waypoint.latitude, waypoint.longitude));

          if (!isItineraryView) {
            setState(() {
              _selectedWaypointIndexMappa = index;
            });
            // Animate the bottom sheet to show more details
            // We can adjust the sheet size based on the selected waypoint if needed,
            // but for now, let's rely on the snap points.
            _sheetController.animateTo(
              _sheetMinSize + 0.25,
              duration: const Duration(milliseconds: 300),
              curve: Curves.easeInOut,
            );
          } else {
            setState(() {
              _selectedWaypointIndex = index;
              for (int i = 0; i < _expandedWaypoints.length; i++) {
                _expandedWaypoints[i] = (i == index);
              }
            });
          }
        },
        child: Stack(
          children: [
            // Shadow for depth
            if (isItineraryView)
              Positioned(
                bottom: 0,
                left: 0,
                right: 0,
                child: Container(
                  height: 4,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withOpacity(0.3),
                        blurRadius: 8,
                        spreadRadius: 1,
                        offset: const Offset(0, 4),
                      ),
                    ],
                  ),
                ),
              ),

            // Marker container
            Container(
              width:
                  isSelectedMappa
                      ? 60
                      : (isSelected ? 52 : (isItineraryView ? 40 : 32)),
              height:
                  isSelectedMappa
                      ? 60
                      : (isSelected ? 52 : (isItineraryView ? 40 : 32)),
              decoration: BoxDecoration(
                color:
                    isSelected | isSelectedMappa
                        ? Colors.green.withOpacity(0.5)
                        : AppColors.primary.withOpacity(0.5),
                shape: BoxShape.circle,
                border: Border.all(color: Colors.white, width: 2),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withOpacity(0.2),
                    blurRadius: 4,
                    offset: const Offset(0, 2),
                  ),
                ],
              ),
              child: Center(
                child: Text(
                  isItineraryView ? '${index}' : '${index + 1}',
                  style: TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.bold,
                    fontSize:
                        isSelectedMappa
                            ? context.r.sp(25)
                            : (isSelected
                                ? context.r.sp(22)
                                : (isItineraryView
                                    ? context.r.sp(16)
                                    : context.r.sp(14))),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  // Build image gallery indicator dots
  Widget _buildImageIndicator() {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: List.generate(
        // _tourDetails!.images.length,
        1,
        (index) => Container(
          width: 8,
          height: 8,
          margin: const EdgeInsets.symmetric(horizontal: 4),
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color:
                _currentImageIndex == index
                    ? AppColors.primary
                    : Colors.white.withOpacity(0.5),
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final screenHeight = MediaQuery.of(context).size.height;
    final screenWidth = MediaQuery.of(context).size.width;

    if (_isLoadingTourDetails || _isLoadingWaypoints) {
      return Scaffold(
        appBar: AppBar(backgroundColor: Colors.white, toolbarHeight: 0.1),
        body: const Center(child: CircularProgressIndicator()),
      );
    }

    // Conditionally render the content based on the selected tab
    Widget mainContent;
    if (_selectedTab == 'Mappa') {
      // Mappa view: Full-screen map with a draggable sheet on top
      mainContent = Stack(
        children: [
          // Full-screen map
          FlutterMap(
            mapController: _mapController,
            options: MapOptions(
              initialCenter:
                  // _waypoints[0].location, // Start with first waypoint
                  _currentPosition != null
                      ? LatLng(
                        _currentPosition!.latitude,
                        _currentPosition!.longitude,
                      )
                      : LatLng(_realWaypoints[0].latitude, _realWaypoints[0].longitude),
              initialZoom: 13.0,
              maxZoom: 16.0,
              interactionOptions: const InteractionOptions(
                flags: InteractiveFlag.all,
              ),
            ),
            children: [
              _baseMapLayer(),
              // Waypoint markers
              MarkerLayer(
                markers:
                    _realWaypoints.asMap().entries.map((entry) {
                      int index = entry.key;
                      Waypoint waypoint = entry.value;
                      return _buildWaypointMarker(
                        index,
                        waypoint,
                        isItineraryView: false,
                      );
                    }).toList(),
              ),

              // Current location marker
              if (_currentPosition != null)
                CurrentLocationLayer(
                  style: LocationMarkerStyle(
                    marker: Container(
                      decoration: BoxDecoration(
                        color: Colors.blue.withOpacity(0.6),
                        shape: BoxShape.circle,
                      ),
                      padding: const EdgeInsets.all(8),
                      child: const Center(
                        child: Icon(
                          Icons.person_pin_circle,
                          color: Colors.white,
                          size: 18,
                        ),
                      ),
                    ),
                    markerSize: const Size.square(40),
                    accuracyCircleColor: Colors.blue.withOpacity(0.3),
                    headingSectorColor: Colors.blue.withOpacity(0.8),
                  ),
                ),
            ],
          ),

          // Back button (positioned on top of the map)
          Positioned(
            top: MediaQuery.of(context).padding.top + context.r.space(8),
            left: 16,
            child: Container(
              width: screenWidth * 0.15,
              height: screenHeight * 0.07,
              decoration: BoxDecoration(
                color: Colors.white,
                shape: BoxShape.circle,
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withOpacity(0.1),
                    blurRadius: 8,
                    offset: const Offset(0, 2),
                  ),
                ],
              ),
              child: IconButton(
                icon: const Icon(
                  Icons.arrow_back,
                  color: AppColors.textPrimary,
                  size: 28,
                ),
                onPressed: () {
                  // Go back to previous screen or tab
                  setState(() {
                    _selectedTab =
                        'About'; // Or 'Mappa' depending on desired flow
                  });
                  _mapAnimationController.reverse();
                },
              ),
            ),
          ),

          if (_tourDetails!.status == "BUILT")
            // if (widget.isGuest == false)
            Positioned(
              top: MediaQuery.of(context).padding.top + context.r.space(8),
              right: 16,
              child: Container(
                width: screenWidth * 0.15,
                height: screenHeight * 0.07,
                decoration: BoxDecoration(
                  color: Colors.blue.shade700,
                  shape: BoxShape.circle,
                ),
                child: IconButton(
                  icon: const Icon(
                    Icons.camera_alt,
                    color: Colors.white,
                    size: 28,
                  ),
                  onPressed: () {
                    if (!widget.isOffline) {
                      _apiService.initializeInferenceModule(
                        widget.tourId,
                        baseUrl: _apiService.getCurrentBaseUrl(),
                      );
                    }
                    unawaited(
                      _analytics.logEvent(
                        name: 'go_to_camera_screen',
                        parameters: {
                          'tour_id': widget.tourId,
                          "source": "map_screen",
                        },
                      ),
                    );
                    //Initialize the inference module for the tour
                    Navigator.push(
                      context,
                      platformPageRoute(
                        builder:
                            (context) => ARCameraScreen(
                              tourId: widget.tourId,
                              latitude: _tourDetails!.latitude,
                              longitude: _tourDetails!.longitude,
                              isOffline: widget.isOffline,
                            ),
                      ),
                    );
                  },
                ),
              ),
            ),

          // Bottom sheet with waypoint info
          DraggableScrollableSheet(
            controller: _sheetController, // Attach the controller
            initialChildSize: _sheetMinSize, // Start with 15% of screen height
            minChildSize: 0.1, // Can collapse to 10% of screen height
            maxChildSize: 1.0, // Can expand to FULL screen height (100%)
            snap: true, // Snap to specific sizes
            snapSizes: const [
              0.1,
              0.3,
              0.6,
              1.0,
            ], // Snap points including full screen
            builder: (context, scrollController) {
              final selectedWaypoint = _realWaypoints[_selectedWaypointIndexMappa];

              return Container(
                decoration: const BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
                ),
                child: CustomScrollView(
                  controller: scrollController,
                  slivers: [
                    // Handle indicator and header (always visible)
                    SliverToBoxAdapter(
                      child: Column(
                        children: [
                          // Handle indicator
                          Center(
                            child: Container(
                              margin: const EdgeInsets.only(top: 12, bottom: 8),
                              width: 40,
                              height: 4,
                              decoration: BoxDecoration(
                                color: Colors.grey.withOpacity(0.3),
                                borderRadius: BorderRadius.circular(2),
                              ),
                            ),
                          ),

                          // Waypoint header
                          Padding(
                            padding: const EdgeInsets.all(16.0),
                            child: Row(
                              children: [
                                // Waypoint image
                                ClipRRect(
                                  borderRadius: BorderRadius.circular(12),
                                  child:
                                      widget.isOffline
                                          ? (_getWaypointImagesFor(
                                                selectedWaypoint,
                                              ).isNotEmpty
                                              ? ZlibImage(
                                                filePath:
                                                    _getWaypointImagesFor(
                                                      selectedWaypoint,
                                                    )[0],
                                                width: 80,
                                                height: 80,
                                                fit: BoxFit.cover,
                                                useCache: false,
                                                errorBuilder:
                                                    (
                                                      context,
                                                      error,
                                                      stackTrace,
                                                    ) =>
                                                        _offlineImagePlaceholder(),
                                              )
                                              : _offlineImagePlaceholder())
                                          : (selectedWaypoint.images.isNotEmpty
                                              ? CachedNetworkImage(
                                                imageUrl:
                                                    "${ApiService.basicUrl}/stream_minio_resource/?waypoint=${selectedWaypoint.id}&file=${selectedWaypoint.images[0]}",
                                                width: 80,
                                                height: 80,
                                                fit: BoxFit.cover,
                                                memCacheWidth: 160,
                                                maxWidthDiskCache: 320,
                                                placeholder:
                                                    (
                                                      context,
                                                      url,
                                                    ) => const Center(
                                                      child:
                                                          CircularProgressIndicator(
                                                            strokeWidth: 2,
                                                          ),
                                                    ),
                                                errorWidget:
                                                    (context, url, error) =>
                                                        _offlineImagePlaceholder(),
                                              )
                                              : _offlineImagePlaceholder()),
                                ),
                                const SizedBox(width: 16),

                                // Waypoint info
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      Text(
                                        selectedWaypoint.category,
                                        style: TextStyle(
                                          fontSize: context.r.sp(14),
                                          color: AppColors.textSecondary,
                                        ),
                                      ),
                                      Text(
                                        selectedWaypoint.title,
                                        style: TextStyle(
                                          fontSize: context.r.sp(18),
                                          fontWeight: FontWeight.bold,
                                          color: AppColors.textPrimary,
                                        ),
                                      ),
                                      Text(
                                        'Tap on markers to navigate',
                                        style: TextStyle(
                                          fontSize: context.r.sp(12),
                                          color: Colors.grey.shade600,
                                          fontStyle: FontStyle.italic,
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                              ],
                            ),
                          ),

                          // Divider
                          Divider(
                            height: 1,
                            thickness: 1,
                            color: Colors.grey.withOpacity(0.2),
                          ),
                        ],
                      ),
                    ),

                    // Expanded content (visible when sheet is dragged up)
                    SliverToBoxAdapter(
                      child: Padding(
                        padding: const EdgeInsets.all(16.0),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            // Description section
                            Text(
                              'description'.tr(),
                              style: TextStyle(
                                fontSize: context.r.sp(18),
                                fontWeight: FontWeight.bold,
                                color: AppColors.textPrimary,
                              ),
                            ),
                            const SizedBox(height: 8),
                            Text(
                              selectedWaypoint.description,
                              style: TextStyle(
                                fontSize: context.r.sp(16),
                                height: 1.5,
                                color: AppColors.textSecondary,
                              ),
                            ),

                            const SizedBox(height: 24),

                            // Tour progress
                            // const Text(
                            //   'Tour Progress',
                            //   style: TextStyle(
                            //     fontSize: context.r.sp(18),
                            //     fontWeight: FontWeight.bold,
                            //     color: AppColors.textPrimary,
                            //   ),
                            // ),
                            // const SizedBox(height: 8),
                            // Text(
                            //   'Waypoint ${_selectedWaypointIndex + 1} of ${_waypoints.length}',
                            //   style: const TextStyle(
                            //     fontSize: context.r.sp(14),
                            //     color: AppColors.textSecondary,
                            //   ),
                            // ),
                            // const SizedBox(height: 8),

                            // Progress bar
                            // Container(
                            //   height: 8,
                            //   decoration: BoxDecoration(
                            //     color: Colors.grey.shade200,
                            //     borderRadius: BorderRadius.circular(4),
                            //   ),
                            //   child: Row(
                            //     children: [
                            //       Container(
                            //         width:
                            //             MediaQuery.of(
                            //               context,
                            //             ).size.width *
                            //             (_selectedWaypointIndex + 1) /
                            //             _waypoints.length *
                            //             0.9, // Adjusted width calculation
                            //         decoration: BoxDecoration(
                            //           color: AppColors.primary,
                            //           borderRadius:
                            //               BorderRadius.circular(4),
                            //         ),
                            //       ),
                            //     ],
                            //   ),
                            // ),
                            const SizedBox(height: 24),

                            // Photos section
                            if (selectedWaypoint.images.isNotEmpty) ...[
                              Text(
                                'photos'.tr(),
                                style: TextStyle(
                                  fontSize: context.r.sp(18),
                                  fontWeight: FontWeight.bold,
                                  color: AppColors.textPrimary,
                                ),
                              ),
                              const SizedBox(height: 12),
                              SizedBox(
                                height: 200,
                                child: ListView.builder(
                                  scrollDirection: Axis.horizontal,
                                  itemCount: selectedWaypoint.images.length,
                                  itemBuilder: (context, index) {
                                    return Padding(
                                      padding: const EdgeInsets.only(right: 12),
                                      child: ClipRRect(
                                        borderRadius: BorderRadius.circular(12),
                                        child:
                                            widget.isOffline
                                                ? (_getWaypointImagesFor(
                                                      selectedWaypoint,
                                                    ).isNotEmpty
                                                    ? ZlibImage(
                                                      filePath:
                                                          _getWaypointImagesFor(
                                                            selectedWaypoint,
                                                          )[index],
                                                      width: 250,
                                                      height: 200,
                                                      fit: BoxFit.cover,
                                                      useCache: false,
                                                      errorBuilder:
                                                          (
                                                            context,
                                                            error,
                                                            stackTrace,
                                                          ) =>
                                                              _offlineImagePlaceholder(),
                                                    )
                                                    : _offlineImagePlaceholder())
                                                : (selectedWaypoint
                                                        .images
                                                        .isNotEmpty
                                                    ? CachedNetworkImage(
                                                      imageUrl:
                                                          "${ApiService.basicUrl}/stream_minio_resource/?waypoint=${selectedWaypoint.id}&file=${selectedWaypoint.images[index]}",
                                                      fit: BoxFit.cover,
                                                      memCacheWidth: 1200,
                                                      maxWidthDiskCache: 1600,
                                                      placeholder:
                                                          (
                                                            context,
                                                            url,
                                                          ) => const Center(
                                                            child:
                                                                CircularProgressIndicator(
                                                                  strokeWidth:
                                                                      2,
                                                                ),
                                                          ),
                                                      errorWidget:
                                                          (
                                                            context,
                                                            url,
                                                            error,
                                                          ) =>
                                                              _offlineImagePlaceholder(),
                                                    )
                                                    : _offlineImagePlaceholder()),
                                      ),
                                    );
                                  },
                                ),
                              ),
                              const SizedBox(height: 24),
                            ],
                            const SizedBox(height: 16),
                            SizedBox(
                              width: double.infinity,
                              child: ElevatedButton.icon(
                                onPressed:
                                    () => _launchMapApp(
                                      selectedWaypoint.latitude,
                                      selectedWaypoint.longitude,
                                    ),
                                icon: const Icon(Icons.navigation),
                                label: Text('navigate_to_waypoint'.tr()),
                                style: ElevatedButton.styleFrom(
                                  backgroundColor: AppColors.primary,
                                  foregroundColor: Colors.white,
                                  padding: const EdgeInsets.symmetric(
                                    vertical: 12,
                                  ),
                                  shape: RoundedRectangleBorder(
                                    borderRadius: BorderRadius.circular(8),
                                  ),
                                ),
                              ),
                            ),

                            // Navigation buttons
                            // Row(
                            //   mainAxisAlignment:
                            //       MainAxisAlignment.spaceBetween,
                            //   children: [
                            //     ElevatedButton.icon(
                            //       onPressed:
                            //           _selectedWaypointIndex > 0
                            //               ? () {
                            //                 setState(() {
                            //                   _selectedWaypointIndex--;
                            //                   _centerMap(
                            //                     LatLng(_waypoints[_selectedWaypointIndex]
                            //                         .latitude, _waypoints[_selectedWaypointIndex].longitude)
                            //                   );
                            //                 });
                            //               }
                            //               : null,
                            //       icon: const Icon(Icons.arrow_back),
                            //       label: const Text('Previous'),
                            //       style: ElevatedButton.styleFrom(
                            //         backgroundColor: AppColors.primary,
                            //         foregroundColor: Colors.white,
                            //         disabledBackgroundColor:
                            //             Colors.grey.shade300,
                            //         disabledForegroundColor:
                            //             Colors.grey.shade500,
                            //       ),
                            //     ),
                            //     ElevatedButton.icon(
                            //       onPressed:
                            //           _selectedWaypointIndex <
                            //                   _waypoints.length - 1
                            //               ? () {
                            //                 setState(() {
                            //                   _selectedWaypointIndex++;
                            //                   _centerMap(
                            //                     LatLng(_waypoints[_selectedWaypointIndex]
                            //                         .latitude, _waypoints[_selectedWaypointIndex].longitude)
                            //                   );
                            //                 });
                            //               }
                            //               : null,
                            //       icon: const Icon(Icons.arrow_forward),
                            //       label: const Text('Next'),
                            //       style: ElevatedButton.styleFrom(
                            //         backgroundColor: AppColors.primary,
                            //         foregroundColor: Colors.white,
                            //         disabledBackgroundColor:
                            //             Colors.grey.shade300,
                            //         disabledForegroundColor:
                            //             Colors.grey.shade500,
                            //       ),
                            //     ),
                            //   ],
                            // ),

                            // Additional information
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
              );
            },
          ),
        ],
      );
    } else {
      // About and Mappa views: Standard scrollable content
      mainContent = SingleChildScrollView(
        physics:
            const AlwaysScrollableScrollPhysics(), // Enable scrolling for these tabs
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Image gallery with pagination
            Stack(
              children: [
                // Image gallery
                SizedBox(
                  height: context.r.heroImageHeight(),
                  width: double.infinity,
                  child: PageView.builder(
                    controller: _pageController,
                    // itemCount: _tourDetails?.images.length,
                    itemCount: 1,
                    onPageChanged: (index) {
                      setState(() {
                        _currentImageIndex = index;
                      });
                    },
                    itemBuilder: (context, index) {
                      if (widget.isOffline &&
                          _offlineTourImagePath != null &&
                          File(_offlineTourImagePath!).existsSync()) {
                        // Modalità Offline: carica l'immagine dal file locale
                        return ZlibImage(
                          filePath: _offlineTourImagePath!,
                          fit: BoxFit.cover,
                          errorBuilder:
                              (context, error, stackTrace) =>
                                  _offlineImagePlaceholder(),
                        );
                      } else if (_tourDetails != null) {
                        // Modalità Online: carica l'immagine dalla rete
                        return CachedNetworkImage(
                          imageUrl:
                              "${ApiService.basicUrl}/stream_minio_resource/?tour=${_tourDetails!.id}",
                          fit: BoxFit.cover,
                          memCacheWidth: 1200,
                          maxWidthDiskCache: 1600,
                          placeholder:
                              (context, url) => const Center(
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                ),
                              ),
                          errorWidget:
                              (context, url, error) =>
                                  _offlineImagePlaceholder(),
                        );
                      }
                      // Fallback nel caso in cui non ci sia nessuna immagine
                      return _offlineImagePlaceholder();
                    },
                  ),
                ),

                // Status bar area
                Container(
                  height: MediaQuery.of(context).padding.top,
                  color: Colors.transparent,
                ),

                // Back button
                Positioned(
                  top: MediaQuery.of(context).padding.top + context.r.space(8),
                  left: 16,
                  child: Container(
                    width: screenWidth * 0.15,
                    height: screenHeight * 0.07,
                    decoration: BoxDecoration(
                      color: Colors.white,
                      shape: BoxShape.circle,
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withOpacity(0.1),
                          blurRadius: 8,
                          offset: const Offset(0, 2),
                        ),
                      ],
                    ),
                    child: IconButton(
                      icon: const Icon(
                        Icons.arrow_back,
                        color: AppColors.textPrimary,
                        size: 28,
                      ),
                      onPressed: () => Navigator.pop(context),
                    ),
                  ),
                ),

                // Image counter
                Positioned(
                  bottom: 16,
                  right: 16,
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 12,
                      vertical: 6,
                    ),
                    decoration: BoxDecoration(
                      color: Colors.black.withOpacity(0.6),
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: Text(
                      '${_currentImageIndex + 1}/1',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: context.r.sp(12),
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                ),

                // Image indicator dots
                Positioned(
                  bottom: 16,
                  left: 0,
                  right: 0,
                  child: _buildImageIndicator(),
                ),
              ],
            ),

            // Category, title, and rating
            Padding(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          "created_by".tr(
                            namedArgs: {'creator': _tourDetails?.creator ?? ''},
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: context.r.sp(12),
                            fontWeight: FontWeight.w500,
                            color: AppColors.textSecondary,
                          ),
                        ),
                      ),
                      // const Spacer(),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          "last_edited_by".tr(
                            namedArgs: {'date': _tourDetails?.lastEdited ?? ''},
                          ),
                          textAlign: TextAlign.end,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: context.r.sp(12),
                            fontWeight: FontWeight.w500,
                            color: AppColors.textSecondary,
                          ),
                        ),
                      ),
                    ],
                  ),

                  Row(
                    crossAxisAlignment:
                        CrossAxisAlignment
                            .start, // Ensures items align at the top
                    children: [
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              ...List.generate(5, (index) {
                                if (index < _tourDetails!.rating.floor()) {
                                  return const Icon(
                                    Icons.star,
                                    color: Colors.amber,
                                    size: 18,
                                  );
                                } else if (index < _tourDetails!.rating) {
                                  return const Icon(
                                    Icons.star_half,
                                    color: Colors.amber,
                                    size: 18,
                                  );
                                } else {
                                  return const Icon(
                                    Icons.star_border,
                                    color: Colors.amber,
                                    size: 18,
                                  );
                                }
                              }),
                              const SizedBox(width: 8),
                              Text(
                                '${_tourDetails!.rating.toStringAsFixed(1).toString()} (${_tourDetails!.reviewCount.toString()})',
                                style: TextStyle(
                                  fontSize: context.r.sp(14),
                                  fontWeight: FontWeight.bold,
                                  color: AppColors.textSecondary,
                                ),
                              ),
                              const SizedBox(width: 15),
                              //Eye icon
                              const Icon(
                                Icons.remove_red_eye,
                                size: 16,
                                color: AppColors.textSecondary,
                              ),
                              Text(
                                _tourDetails!.totViews.toString(),
                                style: TextStyle(
                                  fontSize: context.r.sp(14),
                                  fontWeight: FontWeight.bold,
                                  color: AppColors.textSecondary,
                                ),
                              ),
                            ],
                          ),
                          // const SizedBox(height: 8),
                          Row(
                            children: [
                              Text(
                                _tourDetails!.title,
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  fontSize: context.r.sp(24),
                                  fontWeight: FontWeight.bold,
                                  color: AppColors.textPrimary,
                                ),
                              ),
                              // const SizedBox(width: 135),
                            ],
                          ),
                          Row(
                            children: [
                              const Icon(
                                Icons.location_on,
                                size: 16,
                                color: AppColors.textSecondary,
                              ),
                              const SizedBox(width: 4),
                              Text(
                                _tourDetails!.location,
                                style: TextStyle(
                                  fontSize: context.r.sp(14),
                                  color: AppColors.textSecondary,
                                ),
                              ),
                            ],
                          ),
                        ],
                      ),

                      const Spacer(),
                      if (_tourDetails?.status == "BUILT")
                        // if (widget.isGuest == false) //Debug
                        Padding(
                          padding: const EdgeInsets.only(top: 20.0),
                          child: Center(
                            child: ElevatedButton(
                              onPressed: () {
                                if (!widget.isOffline) {
                                  _apiService.initializeInferenceModule(
                                    _tourDetails!.id,
                                    baseUrl: _apiService.getCurrentBaseUrl(),
                                  );
                                }

                                unawaited(
                                  _analytics.logEvent(
                                    name: "go_to_camera_screen",
                                    parameters: {
                                      "tour_id": widget.tourId,
                                      "source": "about_screen",
                                    },
                                  ),
                                );

                                Navigator.push(
                                  context,
                                  platformPageRoute(
                                    builder:
                                        (context) => ARCameraScreen(
                                          tourId: widget.tourId,
                                          latitude: _tourDetails!.latitude,
                                          longitude: _tourDetails!.longitude,
                                          isOffline: widget.isOffline,
                                        ),
                                  ),
                                );
                              },
                              style: ElevatedButton.styleFrom(
                                backgroundColor: AppColors.primary,
                                foregroundColor: Colors.white,
                                padding: const EdgeInsets.symmetric(
                                  horizontal: 30,
                                  vertical: 10,
                                ),
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(40),
                                ),
                                elevation: 0,
                              ),
                              child: const Icon(
                                Icons.camera_alt,
                                size: 28,
                                color: Colors.white,
                              ),
                            ),
                          ),
                        ),
                    ],
                  ),
                ],
              ),
            ),

            // Navigation tabs (Conditionally shown here)
            Padding(
              // Tabs are always inside the SingleChildScrollView for About/Mappa
              padding: const EdgeInsets.symmetric(horizontal: 15.0),
              child: Row(
                children: [
                  _buildNavTab(
                    icon: Icons.info_outline,
                    label: 'about_tab'.tr(),
                    isSelected: _selectedTab == 'About',
                    onTap: () {
                      setState(() {
                        _selectedTab = 'About';
                      });
                    },
                  ),
                  SizedBox(width: 10),
                  _buildNavTab(
                    icon: Icons.route_outlined,
                    label: 'itinerary_tab'.tr(),
                    isSelected: _selectedTab == 'Itinerario',
                    onTap: () {
                      setState(() {
                        _selectedTab = 'Itinerario';
                      });
                    },
                  ),
                  SizedBox(width: 10),
                  if (_tourDetails != null &&
                      _tourDetails!.category != "INDOOR" &&
                      _tourDetails!.category != "GUIDE")
                    _buildNavTab(
                      icon: Icons.map_outlined,
                      label: 'map_tab'.tr(),
                      // buttonColor: Color.fromARGB(255, 255, 191, 0),
                      // buttonColor: Color.fromARGB(255, 195, 247, 58),
                      buttonColor: Color.fromARGB(255, 178, 237, 197),
                      isSelected: _selectedTab == 'Mappa',
                      onTap: () {
                        setState(() {
                          _selectedTab = 'Mappa';
                        });
                        // Start the animation when switching to Mappa
                        _mapAnimationController.forward();
                      },
                    ),
                ],
              ),
            ),

            const SizedBox(height: 16),

            // Content based on selected tab (About or Mappa)
            if (_selectedTab == 'About') ...[
              // Tour highlights
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16.0),
                child: Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(12),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withOpacity(0.05),
                        blurRadius: 10,
                        offset: const Offset(0, 2),
                      ),
                    ],
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'tour_highlights'.tr(),
                        style: TextStyle(
                          fontSize: context.r.sp(18),
                          fontWeight: FontWeight.bold,
                          color: AppColors.textPrimary,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        _tourDetails!.description,
                        style: TextStyle(
                          fontSize: context.r.sp(14),
                          color: AppColors.textSecondary,
                          height: 1.5,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 24),
              if (!widget.isOffline)
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16.0),
                  child: _buildOfflineSection(),
                ),
              const SizedBox(height: 24),
              // Verified reviews section
              if (!widget.isOffline)
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16.0),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Text(
                            'verified_reviews'.tr(),
                            style: TextStyle(
                              fontSize: context.r.sp(23),
                              fontWeight: FontWeight.bold,
                              color: AppColors.textPrimary,
                            ),
                          ),
                          const SizedBox(width: 8),
                          Text(
                            '(${_tourDetails!.reviewCount})',
                            style: TextStyle(
                              fontSize: context.r.sp(16),
                              color: AppColors.textSecondary,
                            ),
                          ),
                          const Spacer(),
                          if (!widget.isGuest &&
                              !_hasUserAlreadyReviewed &&
                              !_isCheckingUserReview)
                            IconButton(
                              onPressed: () {
                                _showLeaveReviewSheet(_tourDetails!.id);
                              },
                              icon: Icon(
                                Icons.add_circle,
                                color: AppColors.primary,
                                size: 60,
                              ),
                            ),
                        ],
                      ),
                      // const SizedBox(height: 4),
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          Text(
                            _tourDetails!.rating.toStringAsFixed(1).toString(),
                            style: TextStyle(
                              fontSize: context.r.sp(48),
                              fontWeight: FontWeight.bold,
                              color: AppColors.textPrimary,
                            ),
                          ),
                          const SizedBox(width: 16),
                          Padding(
                            padding: const EdgeInsets.only(bottom: 8.0),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  children: [
                                    const Icon(
                                      Icons.star,
                                      color: Colors.amber,
                                      size: 18,
                                    ),
                                    const Icon(
                                      Icons.star,
                                      color: Colors.amber,
                                      size: 18,
                                    ),
                                    const Icon(
                                      Icons.star,
                                      color: Colors.amber,
                                      size: 18,
                                    ),
                                    const Icon(
                                      Icons.star,
                                      color: Colors.amber,
                                      size: 18,
                                    ),
                                    const Icon(
                                      Icons.star_half,
                                      color: Colors.amber,
                                      size: 18,
                                    ),
                                  ],
                                ),
                                Text(
                                  'based_on_reviews'.tr(
                                    namedArgs: {
                                      'count': '${_tourDetails!.reviewCount}',
                                    },
                                  ),
                                  style: TextStyle(
                                    fontSize: context.r.sp(14),
                                    color: AppColors.textSecondary,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 16),
                      //load the first two elements from _reviews
                      if (_isLoadingReviews)
                        const Center(child: CircularProgressIndicator())
                      else
                        ListView.builder(
                          shrinkWrap: true,
                          physics: NeverScrollableScrollPhysics(),
                          itemCount: _reviews.length,
                          itemBuilder: (context, index) {
                            return _buildReviewItem(
                              name: _reviews[index].user,
                              date: _reviews[index].date,
                              rating: _reviews[index].rating,
                              comment: _reviews[index].comment,
                            );
                          },
                        ),
                      const SizedBox(height: 16),
                      SizedBox(
                        width: double.infinity,
                        child: OutlinedButton(
                          onPressed: () {
                            unawaited(
                              _analytics.logEvent(
                                name: 'view_all_reviews',
                                parameters: {
                                  'tour_id': widget.tourId,
                                  "source": "about_screen",
                                },
                              ),
                            );

                            Navigator.push(
                              context,
                              platformPageRoute(
                                builder:
                                    (context) => ReviewListScreen(
                                      tourName: _tourDetails!.title,
                                      tourId: widget.tourId,
                                      isTour: true,
                                      reviewCount: _tourDetails!.reviewCount,
                                    ),
                              ),
                            );
                          },
                          style: OutlinedButton.styleFrom(
                            side: const BorderSide(color: AppColors.primary),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(8),
                            ),
                            padding: const EdgeInsets.symmetric(vertical: 12),
                          ),
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Text(
                                'More',
                                style: TextStyle(
                                  fontSize: context.r.sp(16),
                                  fontWeight: FontWeight.bold,
                                  color: AppColors.primary,
                                ),
                              ),
                              SizedBox(width: 4),
                              Icon(
                                Icons.keyboard_arrow_down,
                                size: 20,
                                color: AppColors.primary,
                              ),
                            ],
                          ),
                        ),
                      ),
                      const SizedBox(height: 12),

                      // Pulsante Report Tour (outline rosso con icona danger)
                      SizedBox(
                        width: double.infinity,
                        child: OutlinedButton.icon(
                          onPressed: () async {
                            ScaffoldMessenger.of(context).showSnackBar(
                              SnackBar(
                                content: Text('report_sent'.tr()),
                                backgroundColor: Colors.red,
                              ),
                            );

                            try {
                              await _apiService.sendReport(
                                widget.tourId,
                                baseUrl: _apiService.getCurrentBaseUrl(),
                              );
                              unawaited(
                                _analytics.logEvent(
                                  name: "report_tour",
                                  parameters: {
                                    "tour_id": widget.tourId,
                                    "source": "about_screen",
                                  },
                                ),
                              );
                            } catch (e) {
                              if (mounted) {
                                ScaffoldMessenger.of(context).showSnackBar(
                                  SnackBar(
                                    content: Text('report_failed'.tr()),
                                    backgroundColor: Colors.red,
                                  ),
                                );
                              }
                            }
                          },
                          icon: const Icon(Icons.report, color: Colors.red),
                          label: Text(
                            'report_tour'.tr(),
                            style: const TextStyle(color: Colors.red),
                          ),
                          style: OutlinedButton.styleFrom(
                            side: const BorderSide(color: Colors.red),
                            foregroundColor: Colors.red,
                            padding: const EdgeInsets.symmetric(vertical: 12),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(8),
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
            ] else if (_selectedTab == 'Itinerario') ...[
              if (_tourDetails != null &&
                  _tourDetails!.category != "INDOOR" &&
                  _tourDetails!.category != "GUIDE")
                // Interactive Map view using flutter_map
                Padding(
                  padding: const EdgeInsets.all(16.0),
                  child: Container(
                    height: 300, // Fixed height for the map in Mappa tab
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(12),
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withOpacity(0.1),
                          blurRadius: 10,
                          offset: const Offset(0, 4),
                        ),
                      ],
                    ),
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(12),
                      child: FlutterMap(
                        mapController: _mapController,
                        options: MapOptions(
                          initialCameraFit: _getInitialCameraFit(),
                          maxZoom: 16.0,
                          interactionOptions: const InteractionOptions(
                            flags: InteractiveFlag.all,
                          ),
                        ),
                        children: [
                          _baseMapLayer(),

                          // Current location marker
                          if (_currentPosition != null)
                            CurrentLocationLayer(
                              style: LocationMarkerStyle(
                                marker: Container(
                                  decoration: BoxDecoration(
                                    color: AppColors.primary.withOpacity(0.6),
                                    shape: BoxShape.circle,
                                  ),
                                  padding: const EdgeInsets.all(8),
                                  child: const Center(
                                    child: Icon(
                                      Icons.person_pin_circle,
                                      color: Colors.white,
                                      size: 18,
                                    ),
                                  ),
                                ),
                                markerSize: const Size.square(40),
                                accuracyCircleColor: AppColors.primary
                                    .withOpacity(0.3),
                                headingSectorColor: AppColors.primary
                                    .withOpacity(0.8),
                              ),
                            ),

                          // Waypoints markers
                          MarkerLayer(
                            markers:
                                _waypoints.asMap().entries.map((entry) {
                                  int index = entry.key;
                                  Waypoint waypoint = entry.value;
                                  return _buildWaypointMarker(
                                    index,
                                    waypoint,
                                    isItineraryView: true,
                                  );
                                }).toList(),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),

              if (_waypoints.isNotEmpty) ...[
                ..._waypoints.asMap().entries.expand((entry) {
                  int index = entry.key;
                  Waypoint waypoint = entry.value;

                  List<Widget> waypointWidgets = [];

                  // Aggiungi il waypoint principale
                  waypointWidgets.add(
                    _buildWaypointItem(
                      waypointIndex: waypoint.id,
                      index: index,
                      title: waypoint.title,
                      subtitle: waypoint.subtitle,
                      description: waypoint.description,
                      images: waypoint.images,
                      tourCategory: _tourDetails?.category ?? 'MIXED',
                      latitude: waypoint.latitude,
                      longitude: waypoint.longitude,
                      isPreliminaryInfo: waypoint.isPreliminaryInfo,
                      subWaypoints: waypoint.subWaypoints,
                      isSubWaypoint: false,
                    ),
                  );

                  return waypointWidgets;
                }).toList(),
              ] else
                const Padding(
                  padding: EdgeInsets.all(16.0),
                  child: Text('No waypoints available'),
                ),
            ],

            // Add space at the bottom for non-Itinerario tabs
            const SizedBox(height: 40),
          ],
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(
        backgroundColor: Colors.white, // o AppColors.background
        toolbarHeight: 0.1,
      ),
      body: mainContent, // Directly use the conditionally rendered content
    );
  }

  Widget _buildNavTab({
    required IconData icon,
    required String label,
    required bool isSelected,
    required VoidCallback onTap,
    Color? buttonColor,
  }) {
    return Expanded(
      child: GestureDetector(
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 12),
          decoration: BoxDecoration(
            color:
                buttonColor ??
                (isSelected ? AppColors.primary : Colors.transparent),
            // color: isSelected ? AppColors.primary : Colors.transparent,
            borderRadius: BorderRadius.circular(24),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                icon,
                size: 20,
                color:
                    buttonColor != null
                        ? Colors.black
                        : (isSelected ? Colors.black : AppColors.textSecondary),
              ),
              const SizedBox(width: 6),
              Flexible(
                child: Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  softWrap: false,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: context.r.sp(14),
                    fontWeight:
                        isSelected ? FontWeight.bold : FontWeight.normal,
                    color:
                        buttonColor != null
                            ? Colors.black
                            : (isSelected
                                ? Colors.black
                                : AppColors.textSecondary),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  CameraFit _getInitialCameraFit() {
    List<LatLng> pointsForBounds =
        _realWaypoints
            .map((waypoint) => LatLng(waypoint.latitude, waypoint.longitude))
            .toList();

    if (_currentPosition != null) {
      pointsForBounds.add(
        LatLng(_currentPosition!.latitude, _currentPosition!.longitude),
      );
    }

    if (pointsForBounds.isEmpty) {
      if (_tourDetails != null) {
        if (_currentPosition == null) {
          pointsForBounds.add(
            LatLng(_tourDetails!.latitude, _tourDetails!.longitude),
          );
        }
        return CameraFit.coordinates(coordinates: pointsForBounds);
      }
    }

    return CameraFit.bounds(
      bounds: LatLngBounds.fromPoints(pointsForBounds),
      padding: const EdgeInsets.all(50.0),
    );
  }

  Widget _buildWaypointItem({
    required int waypointIndex,
    required int index,
    required String title,
    required String subtitle,
    required String description,
    required List<String> images,
    required String tourCategory,
    required double latitude,
    required double longitude,
    required bool isPreliminaryInfo,
    List<Waypoint>? subWaypoints,
    int? parentIndex,
    bool isSubWaypoint = false,
  }) {
    final bool isScanned = !isPreliminaryInfo && _scannedWaypoints.contains(waypointIndex);

    // Determina se questo item è espanso
    bool isExpanded;
    if (isSubWaypoint && parentIndex != null) {
      // Per sub-waypoints, controlla nella mappa _expandedSubWaypoints
      isExpanded = _expandedSubWaypoints[parentIndex]?[index] ?? false;
    } else {
      // Per waypoints principali, usa _expandedWaypoints
      isExpanded =
          index < _expandedWaypoints.length ? _expandedWaypoints[index] : false;
    }

    return Padding(
      padding: const EdgeInsets.only(bottom: 8.0),
      child: Column(
        children: [
          // Waypoint header
          Stack(
            children: [
              Container(
                margin: EdgeInsets.symmetric(
                  horizontal:
                      isSubWaypoint
                          ? 32.0
                          : 16.0, // Indentazione per sub-waypoints
                  vertical: 4.0,
                ),
                decoration: BoxDecoration(
                  color: isPreliminaryInfo ? AppColors.primary.withOpacity(0.06) : (isSubWaypoint ? Colors.grey.shade50 : Colors.white),
                  borderRadius: BorderRadius.circular(12),
                  border: isPreliminaryInfo 
                    ? Border.all(color: AppColors.primary.withOpacity(0.25)) :
                      (isSubWaypoint
                          ? Border.all(color: Colors.grey.shade200)
                          : null),
                  boxShadow:
                      isSubWaypoint
                          ? []
                          : [
                            BoxShadow(
                              color: Colors.black.withOpacity(0.08),
                              blurRadius: 8,
                              offset: const Offset(0, 2),
                            ),
                          ],
                ),
                child: Material(
                  color: Colors.transparent,
                  child: InkWell(
                    onTap: () {
                      setState(() {
                        if (isSubWaypoint && parentIndex != null) {
                          // Logica per sub-waypoints: chiudi solo gli altri sub-waypoints dello stesso parent
                          if (_expandedSubWaypoints[parentIndex] != null) {
                            for (
                              int i = 0;
                              i < _expandedSubWaypoints[parentIndex]!.length;
                              i++
                            ) {
                              if (i != index) {
                                _expandedSubWaypoints[parentIndex]![i] = false;
                              }
                            }
                            _expandedSubWaypoints[parentIndex]![index] =
                                !_expandedSubWaypoints[parentIndex]![index];
                          }
                          // NON centrare la mappa per i sub-waypoints
                        } else {
                          // Logica per waypoints principali: chiudi tutti gli altri waypoints principali
                          if (index >= 0 && index < _expandedWaypoints.length) {
                            for (
                              int i = 0;
                              i < _expandedWaypoints.length;
                              i++
                            ) {
                              if (i != index) {
                                _expandedWaypoints[i] = false;
                                // Chiudi anche tutti i sub-waypoints quando si chiude un waypoint principale
                                if (_expandedSubWaypoints[i] != null) {
                                  for (
                                    int j = 0;
                                    j < _expandedSubWaypoints[i]!.length;
                                    j++
                                  ) {
                                    _expandedSubWaypoints[i]![j] = false;
                                  }
                                }
                              }
                            }
                            _expandedWaypoints[index] =
                                !_expandedWaypoints[index];
                            _selectedWaypointIndex = index;

                            // Centra la mappa SOLO per waypoints principali
                            if (!isPreliminaryInfo && index < _waypoints.length &&
                                _selectedTab == 'Itinerario' &&
                                (tourCategory != "INDOOR" &&
                                    tourCategory != "GUIDE")) {
                              _centerMap(
                                LatLng(
                                  _waypoints[index].latitude,
                                  _waypoints[index].longitude,
                                ),
                              );
                            }
                          }
                        }
                      });
                    },
                    borderRadius: BorderRadius.circular(12),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 16.0,
                        vertical: 16.0,
                      ),
                      child: Row(
                        children: [
                          // Waypoint number con logica degli indici corretta
                          // Container(
                          //   width: isSubWaypoint ? 24 : 28,
                          //   height: isSubWaypoint ? 24 : 28,
                          //   decoration: BoxDecoration(
                          //     color:
                          //         isSubWaypoint
                          //             ? AppColors.primary.withOpacity(0.7)
                          //             : AppColors.primary,
                          //     shape: BoxShape.circle,
                          //     border: Border.all(
                          //       color: Colors.white,
                          //       width: 1.5,
                          //     ),
                          //     boxShadow: [
                          //       BoxShadow(
                          //         color: Colors.black.withOpacity(0.2),
                          //         blurRadius: 3,
                          //         offset: const Offset(0, 1),
                          //       ),
                          //     ],
                          //   ),
                          //   child: Center(
                          //     child: Text(
                          //       // Logica corretta per gli indici
                          //       isSubWaypoint
                          //           ? '${(parentIndex ?? 0) + 1}.${index + 1}' // Sub-waypoint: 2.1, 2.2, etc.
                          //           : '${index + 1}', // Waypoint principale: 1, 2, 3, etc.
                          //       style: TextStyle(
                          //         color: Colors.white,
                          //         fontWeight: FontWeight.bold,
                          //         fontSize: isSubWaypoint ? 10 : 12,
                          //       ),
                          //     ),
                          //   ),
                          // ),
                          Container(
                            width: isSubWaypoint ? 24 : 28,
                            height: isSubWaypoint ? 24 : 28,
                            decoration: BoxDecoration(
                              color: isPreliminaryInfo
                                  ? AppColors.primary.withOpacity(0.15)
                                  : (isSubWaypoint
                                      ? AppColors.primary.withOpacity(0.7)
                                      : AppColors.primary),
                              shape: BoxShape.circle,
                              border: Border.all(
                                color: isPreliminaryInfo ? AppColors.primary : Colors.white,
                                width: 1.5,
                              ),
                              boxShadow: [
                                BoxShadow(
                                  color: Colors.black.withOpacity(0.2),
                                  blurRadius: 3,
                                  offset: const Offset(0, 1),
                                ),
                              ],
                            ),
                            child: Center(
                              child: isPreliminaryInfo
                                  ? Icon(
                                      Icons.info_outline,
                                      size: isSubWaypoint ? 14 : 16,
                                      color: AppColors.primary,
                                    )
                                  : Text(
                                      isSubWaypoint
                                          ? '${(parentIndex ?? 0)}.${index + 1}'
                                          : '${index}',
                                      style: TextStyle(
                                        color: Colors.white,
                                        fontWeight: FontWeight.bold,
                                        fontSize: isSubWaypoint ? 10 : 12,
                                      ),
                                    ),
                            ),
                          ),
                          const SizedBox(width: 16),

                          // Waypoint name
                          // Expanded(
                          //   child: Text(
                          //     title,
                          //     style: TextStyle(
                          //       fontSize: isSubWaypoint ? 14 : 16,
                          //       fontWeight: FontWeight.w500,
                          //       color: AppColors.textSecondary,
                          //     ),
                          //   ),
                          // ),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                if (isPreliminaryInfo)
                                  Padding(
                                    padding: const EdgeInsets.only(bottom: 4),
                                    child: Text(
                                      'preliminary_info'.tr(),
                                      style: TextStyle(
                                        fontSize: context.r.sp(11),
                                        fontWeight: FontWeight.w700,
                                        color: AppColors.primary,
                                      ),
                                    ),
                                  ),
                                Text(
                                  title,
                                  style: TextStyle(
                                    fontSize: isSubWaypoint ? 14 : 16,
                                    fontWeight: isPreliminaryInfo ? FontWeight.w700 : FontWeight.w500,
                                    color: isPreliminaryInfo
                                        ? AppColors.textPrimary
                                        : AppColors.textSecondary,
                                  ),
                                ),
                              ],
                            ),
                          ),

                          // Expand/collapse icon
                          Icon(
                            (isExpanded)
                                ? Icons.keyboard_arrow_up
                                : Icons.keyboard_arrow_down,
                            color: AppColors.textSecondary,
                            size: isSubWaypoint ? 20 : 24,
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
              if (isScanned)
                Positioned(
                  top: isSubWaypoint ? 6 : 8,
                  right: isSubWaypoint ? 38 : 22,
                  child: Container(
                    width: 24,
                    height: 24,
                    decoration: BoxDecoration(
                      color: Colors.green,
                      shape: BoxShape.circle,
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withOpacity(0.2),
                          blurRadius: 4,
                          offset: const Offset(0, 2),
                        ),
                      ],
                    ),
                    child: const Icon(
                      Icons.check,
                      color: Colors.white,
                      size: 16,
                    ),
                  ),
                ),
            ],
          ),

          // Waypoint content (expanded)
          if (isExpanded)
            Container(
              margin: EdgeInsets.fromLTRB(
                isSubWaypoint ? 32.0 : 16.0,
                0,
                isSubWaypoint ? 32.0 : 16.0,
                8.0,
              ),
              decoration: BoxDecoration(
                color: isSubWaypoint ? Colors.grey.shade50 : Colors.white,
                borderRadius: BorderRadius.circular(12),
                border:
                    isSubWaypoint
                        ? Border.all(color: Colors.grey.shade200)
                        : null,
                boxShadow:
                    isSubWaypoint
                        ? []
                        : [
                          BoxShadow(
                            color: Colors.black.withOpacity(0.08),
                            blurRadius: 8,
                            offset: const Offset(0, 2),
                          ),
                        ],
              ),
              child: Padding(
                padding: const EdgeInsets.all(16.0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Description
                    Text(
                      description,
                      style: TextStyle(
                        fontSize: context.r.sp(14),
                        color: AppColors.textSecondary,
                        height: 1.5,
                      ),
                    ),

                    // Images (if any)
                    if (images.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.symmetric(vertical: 16.0),
                        child: SizedBox(
                          height: 100,
                          child: ListView.builder(
                            scrollDirection: Axis.horizontal,
                            itemCount:
                                widget.isOffline
                                    ? _offlineImagesByWaypoint[waypointIndex]
                                        ?.length
                                    : images.length,
                            addAutomaticKeepAlives: true,
                            itemBuilder: (context, imageIndex) {
                              return Padding(
                                padding: const EdgeInsets.only(right: 8.0),
                                child: ClipRRect(
                                  borderRadius: BorderRadius.circular(8.0),
                                  child:
                                      widget.isOffline
                                          ? (() {
                                            final offlineList =
                                                _offlineImagesByWaypoint[waypointIndex] ??
                                                const <String>[];
                                            if (imageIndex <
                                                    offlineList.length &&
                                                offlineList[imageIndex]
                                                    .isNotEmpty) {
                                              return ZlibImage(
                                                filePath:
                                                    offlineList[imageIndex],
                                                width: 150,
                                                height: 100,
                                                fit: BoxFit.cover,
                                                useCache: false,
                                                errorBuilder: (
                                                  context,
                                                  error,
                                                  stackTrace,
                                                ) {
                                                  return Container(
                                                    height: 100,
                                                    width: 150,
                                                    decoration: BoxDecoration(
                                                      color:
                                                          Colors.grey.shade300,
                                                      borderRadius:
                                                          BorderRadius.circular(
                                                            8.0,
                                                          ),
                                                    ),
                                                    child: Icon(
                                                      Icons.image_not_supported,
                                                      color:
                                                          Colors.grey.shade600,
                                                    ),
                                                  );
                                                },
                                              );
                                            } else {
                                              return Container(
                                                height: 100,
                                                width: 150,
                                                decoration: BoxDecoration(
                                                  color: Colors.grey.shade300,
                                                  borderRadius:
                                                      BorderRadius.circular(
                                                        8.0,
                                                      ),
                                                ),
                                                child: Icon(
                                                  Icons.image_not_supported,
                                                  color: Colors.grey.shade600,
                                                ),
                                              );
                                            }
                                          })()
                                          : CachedNetworkImage(
                                            imageUrl:
                                                "${ApiService.basicUrl}/stream_minio_resource/?waypoint=$waypointIndex&file=${images[imageIndex]}",
                                            width: 150,
                                            height: 100,
                                            fit: BoxFit.cover,
                                            placeholder:
                                                (context, url) => const Center(
                                                  child:
                                                      CircularProgressIndicator(
                                                        strokeWidth: 2,
                                                      ),
                                                ),
                                            errorWidget: (context, url, error) {
                                              return Container(
                                                height: 100,
                                                width: 150,
                                                decoration: BoxDecoration(
                                                  color: Colors.grey.shade300,
                                                  borderRadius:
                                                      BorderRadius.circular(
                                                        8.0,
                                                      ),
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
                        ),
                      ),

                    // Navigate button - SOLO per waypoints principali
                    if (!isPreliminaryInfo && !isSubWaypoint &&
                        _tourDetails!.category != "INDOOR" &&
                        _tourDetails!.category != "GUIDE") ...[
                      const SizedBox(height: 16),
                      SizedBox(
                        width: double.infinity,
                        child: ElevatedButton.icon(
                          onPressed: () => _launchMapApp(latitude, longitude),
                          icon: const Icon(Icons.navigation),
                          label: Text('navigate_to_waypoint'.tr()),
                          style: ElevatedButton.styleFrom(
                            backgroundColor: AppColors.primary,
                            foregroundColor: Colors.white,
                            padding: const EdgeInsets.symmetric(vertical: 12),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(8),
                            ),
                          ),
                        ),
                      ),
                    ],

                    // if(!isSubWaypoint && _tourDetails?.status != "BUILT" && _tourDetails?.category == "GUIDE") ...[
                    // if(!isSubWaypoint && _tourDetails?.category == "GUIDE") ...[
                    if (!isSubWaypoint) ...[
                      const SizedBox(height: 8),
                      SizedBox(
                        width: double.infinity,
                        child: OutlinedButton.icon(
                          onPressed: () {
                            Navigator.push(
                              context,
                              MaterialPageRoute(
                                builder:
                                    (context) => ConsultationScreen(
                                      tourId: widget.tourId,
                                      waypointId: waypointIndex,
                                      landmarkName: title,
                                      landmarkDescription: description,
                                      landmarkImages: images,
                                      isOffline: widget.isOffline,
                                    ),
                              ),
                            );
                          },
                          icon: const Icon(
                            Icons.art_track_outlined,
                            color: AppColors.primary,
                          ),
                          label: Text('open_resource_consultation'.tr()),
                          style: OutlinedButton.styleFrom(
                            side: BorderSide(color: AppColors.primary),
                            foregroundColor: AppColors.primary,
                            padding: const EdgeInsets.symmetric(vertical: 12),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(8),
                            ),
                          ),
                        ),
                      ),
                    ],

                    // Sub-waypoints SOLO per waypoints principali
                    if (!isSubWaypoint &&
                        subWaypoints != null &&
                        subWaypoints.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: 16.0),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'Sub-locations',
                              style: TextStyle(
                                fontSize: context.r.sp(16),
                                fontWeight: FontWeight.bold,
                                color: AppColors.textPrimary,
                              ),
                            ),
                            const SizedBox(height: 8),
                            // Renderizza i sub-waypoints come waypoint items separati
                            ...subWaypoints.asMap().entries.map((entry) {
                              int subIndex = entry.key;
                              Waypoint sub = entry.value;
                              return _buildWaypointItem(
                                waypointIndex: sub.id,
                                index: subIndex,
                                title: sub.title,
                                subtitle: sub.subtitle,
                                description: sub.description,
                                images: sub.images,
                                tourCategory: tourCategory,
                                latitude: sub.latitude,
                                longitude: sub.longitude,
                                isPreliminaryInfo: sub.isPreliminaryInfo,
                                parentIndex:
                                    index, // Passa l'indice del waypoint principale
                                isSubWaypoint:
                                    true, // Identifica come sub-waypoint
                              );
                            }).toList(),
                          ],
                        ),
                      ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildSubWaypointItem({
    required Waypoint subWaypoint,
    required int parentIndex,
    required int subIndex,
  }) {
    return Container(
      margin: const EdgeInsets.only(left: 16.0, top: 8.0),
      padding: const EdgeInsets.all(12.0),
      decoration: BoxDecoration(
        color: Colors.grey.shade50,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.grey.shade200),
      ),
      child: Row(
        children: [
          // Numero sub-waypoint
          Container(
            width: 24,
            height: 24,
            decoration: BoxDecoration(
              color: AppColors.primary.withOpacity(0.7),
              shape: BoxShape.circle,
            ),
            child: Center(
              child: Text(
                '${parentIndex + 1}.${subIndex + 1}',
                style: TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.bold,
                  fontSize: context.r.sp(10),
                ),
              ),
            ),
          ),
          const SizedBox(width: 12),
          // Contenuto sub-waypoint
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  subWaypoint.title,
                  style: TextStyle(
                    fontSize: context.r.sp(14),
                    fontWeight: FontWeight.w500,
                    color: AppColors.textPrimary,
                  ),
                ),
                if (subWaypoint.description.isNotEmpty)
                  Text(
                    subWaypoint.description,
                    style: TextStyle(
                      fontSize: context.r.sp(12),
                      color: AppColors.textSecondary,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
              ],
            ),
          ),
          // Bottone navigazione
          IconButton(
            onPressed:
                () =>
                    _launchMapApp(subWaypoint.latitude, subWaypoint.longitude),
            icon: Icon(Icons.navigation, color: AppColors.primary, size: 20),
          ),
        ],
      ),
    );
  }

  Widget _buildReviewItem({
    required String name,
    required String date,
    required double rating,
    required String comment,
    String imageUrl = "",
  }) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.05),
            blurRadius: 10,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              // User avatar
              CircleAvatar(
                radius: 20,
                backgroundImage:
                    imageUrl.isNotEmpty ? AssetImage(imageUrl) : null,
                child:
                    imageUrl.isEmpty
                        ? const Icon(
                          Icons.person,
                          size: 24,
                          color: AppColors.textSecondary,
                        )
                        : null,
              ),
              const SizedBox(width: 12),

              // User name and date
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      name,
                      style: TextStyle(
                        fontSize: context.r.sp(16),
                        fontWeight: FontWeight.bold,
                        color: AppColors.textPrimary,
                      ),
                    ),
                    Text(
                      date,
                      style: TextStyle(
                        fontSize: context.r.sp(12),
                        color: AppColors.textSecondary,
                      ),
                    ),
                  ],
                ),
              ),

              // Rating
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: Colors.amber.shade100,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.star, color: Colors.amber, size: 16),
                    const SizedBox(width: 4),
                    Text(
                      rating.toStringAsFixed(1).toString(),
                      style: TextStyle(
                        fontSize: context.r.sp(14),
                        fontWeight: FontWeight.bold,
                        color: AppColors.textPrimary,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),

          const SizedBox(height: 12),

          // Review comment
          Text(
            comment,
            style: TextStyle(
              fontSize: context.r.sp(14),
              color: AppColors.textSecondary,
              height: 1.5,
            ),
          ),

          const SizedBox(height: 8),

          // Read more button
          // GestureDetector(
          //   onTap: () {},
          //   child: const Text(
          //     'Read more',
          //     style: TextStyle(
          //       fontSize: context.r.sp(14),
          //       fontWeight: FontWeight.bold,
          //       color: AppColors.primary,
          //     ),
          //   ),
          // ),
        ],
      ),
    );
  }

  void _showLeaveReviewSheet(int tourId) {
    if (widget.isGuest) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('guest_review_not_allowed'.tr()),
          backgroundColor: Colors.red,
        ),
      );
      return;
    }
    
    showModalBottomSheet(
      context: context,
      isScrollControlled: true, // Allows the sheet to be scrollable
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (context) {
        // Use a StatefulBuilder to manage the state of the stars within the sheet
        return StatefulBuilder(
          builder: (BuildContext context, StateSetter setState) {
            return Padding(
              padding: EdgeInsets.only(
                bottom: MediaQuery.of(context).viewInsets.bottom,
                left: 16,
                right: 16,
                top: 16,
              ),
              child: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Center(
                      child: Container(
                        width: 40,
                        height: 4,
                        decoration: BoxDecoration(
                          color: Colors.grey.shade300,
                          borderRadius: BorderRadius.circular(2),
                        ),
                      ),
                    ),
                    const SizedBox(height: 16),
                    Center(
                      child: Text(
                        'leave_review'.tr(),
                        style: TextStyle(
                          fontSize: context.r.sp(20),
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                    const SizedBox(height: 16),
                    // Star rating
                    Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: List.generate(5, (index) {
                        return IconButton(
                          onPressed: () {
                            setState(() {
                              _userRating = index + 1.0;
                            });
                          },
                          icon: Icon(
                            index < _userRating
                                ? Icons.star
                                : Icons.star_border,
                            color: Colors.amber,
                            size: 55,
                          ),
                        );
                      }),
                    ),
                    const SizedBox(height: 16),
                    Text(
                      'comments'.tr(),
                      style: TextStyle(
                        fontSize: context.r.sp(16),
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 8),
                    // Comments text field
                    Container(
                      decoration: BoxDecoration(
                        color:
                            Colors.white, // Background color of the container
                        borderRadius: BorderRadius.circular(
                          10.0,
                        ), // Optional: rounded corners for the container
                        boxShadow: [
                          BoxShadow(
                            color: Colors.grey.withOpacity(
                              0.5,
                            ), // Color of the shadow
                            spreadRadius:
                                1, // How much the shadow should spread
                            blurRadius: 3, // How blurry the shadow should be
                            offset: Offset(0, 3), // Offset of the shadow (x, y)
                          ),
                        ],
                      ),
                      child: TextField(
                        controller: _reviewController,
                        maxLines: 5,
                        decoration: InputDecoration(
                          hintText: 'comment_hint'.tr(),
                          border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(12),
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(height: 24),
                    // Action buttons
                    Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        TextButton(
                          style: TextButton.styleFrom(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 32,
                              vertical: 12,
                            ),
                            textStyle: TextStyle(fontSize: context.r.sp(20)),
                          ),
                          onPressed: () {
                            Navigator.pop(context); // Close the sheet
                          },
                          child: Text('cancel'.tr()),
                        ),
                        const SizedBox(width: 25),
                        TextButton(
                          style: TextButton.styleFrom(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 32,
                              vertical: 12,
                            ),
                            backgroundColor: AppColors.primary,
                            foregroundColor: Colors.white,
                            textStyle: TextStyle(fontSize: context.r.sp(20)),
                          ),
                          onPressed: () {
                            final rating = _userRating;
                            final comment = _reviewController.text;

                            _apiService.leaveReview(
                              tourId,
                              rating,
                              comment,
                              baseUrl: _apiService.getCurrentBaseUrl(),
                            );

                            if (mounted) {
                              setState(() {
                                _hasUserAlreadyReviewed = true;
                              });
                            }

                            unawaited(
                              _analytics.logEvent(
                                name: 'leave_review',
                                parameters: {
                                  'tour_id': tourId,
                                  'rating': rating,
                                  "source": "about_screen",
                                },
                              ),
                            );
                            _loadData();

                            Navigator.pop(context); // Close the sheet

                            // Optionally, show a confirmation message
                            ScaffoldMessenger.of(context).showSnackBar(
                              SnackBar(
                                content: Text('review_success'.tr()),
                                backgroundColor: Colors.green,
                              ),
                            );
                          },
                          child: Text('send'.tr()),
                        ),
                      ],
                    ),
                    const SizedBox(height: 16),
                  ],
                ),
              ),
            );
          },
        );
      },
    );
  }

  Widget _buildOfflineSection() {
    final bool canDownloadOffline =
        _isAvailableOffline || _tourDetails?.status == "BUILT";
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.05),
            blurRadius: 10,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                _isAvailableOffline ? Icons.offline_bolt : Icons.cloud_download,
                color: AppColors.primary,
              ),
              const SizedBox(width: 12),
              Text(
                "offline_access".tr(),
                style: TextStyle(
                  fontSize: context.r.sp(16),
                  fontWeight: FontWeight.w600,
                  color: AppColors.textPrimary,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            _isAvailableOffline
                ? "tour_available_offline".tr()
                : "download_tour_offline_description".tr(),
            style: TextStyle(
              fontSize: context.r.sp(14),
              color: AppColors.textSecondary,
            ),
          ),
          const SizedBox(height: 16),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton.icon(
              // onPressed: _isDownloading ? null : (_isAvailableOffline ? _confirmRemoveOfflineTour : _downloadTourOffline),
              onPressed:
                  (_isDownloading || !canDownloadOffline)
                      ? null
                      : (_isAvailableOffline
                          ? _confirmRemoveOfflineTour
                          : _downloadTourOffline),
              icon:
                  _isDownloading
                      ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(
                          valueColor: AlwaysStoppedAnimation<Color>(
                            Colors.white,
                          ),
                          strokeWidth: 2,
                        ),
                      )
                      : Icon(
                        _isAvailableOffline
                            ? Icons.delete_outline
                            : Icons.download,
                      ),
              label: Text(
                _isDownloading
                    ? "downloading".tr()
                    : (_isAvailableOffline
                        ? "remove".tr()
                        : "download_for_offline".tr()),
              ),
              style: ElevatedButton.styleFrom(
                backgroundColor:
                    !canDownloadOffline
                        ? Colors.grey
                        : (_isAvailableOffline
                            ? Colors.red
                            : AppColors.primary),
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(vertical: 12),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(8),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
