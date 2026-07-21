import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';
import 'package:connectivity_plus/connectivity_plus.dart';
import 'main.dart';
import 'models/app_colors.dart';
import 'elements/travel_list_item_card.dart';
import 'tour_details_page.dart';
import "category_detail_screen.dart";
import "search_screen.dart";
import 'user_details.dart';
import 'services/tour_service.dart';
import 'services/offline_tour_service.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import "package:easy_localization/easy_localization.dart";
import "elements/zlib_image.dart";
import 'package:geolocator/geolocator.dart';
import 'providers/home_providers.dart'; // Importa i nuovi provider
import 'services/analytics_service.dart';
import 'utils/responsive.dart';
import 'utils/platform_page_route.dart';

class TravelExplorerScreen extends ConsumerStatefulWidget {
  final bool isGuest;

  const TravelExplorerScreen({Key? key, required this.isGuest})
    : super(key: key);

  @override
  ConsumerState<TravelExplorerScreen> createState() =>
      _TravelExplorerScreenState();
}

class _TravelExplorerScreenState extends ConsumerState<TravelExplorerScreen>
    with RouteAware {
  late TourService _tourService;
  late OfflineStorageService _offlineService;
  late AnalyticsService _analytics;

  // State for offline data (local state is fine for offline as it's fast)
  List<Map<String, dynamic>> _offlineTours = [];
  bool _isLoadingOfflineTours = true;

  // State for connectivity
  bool _isOnline = true;
  bool _isCheckingConnection = true;
  late StreamSubscription<List<ConnectivityResult>> _connectivitySubscription;

  String? _lastLoadedLanguage;
  String? _lastLoadedBaseUrl;

  @override
  void initState() {
    super.initState();
    _tourService = ref.read(tourServiceProvider);
    _offlineService = ref.read(offlineStorageServiceProvider);
    _analytics = ref.read(analyticsServiceProvider);

    _checkInitialConnectivity();
    _connectivitySubscription = Connectivity().onConnectivityChanged.listen(
      (_) => _updateConnectionStatus(),
    );

    // Carica i dati offline all'avvio
    _loadOfflineTours();
  }

  Future<void> _checkInitialConnectivity() async {
    if (mounted) setState(() => _isCheckingConnection = true);
    await _updateConnectionStatus();
    if (mounted) setState(() => _isCheckingConnection = false);
  }

  Future<void> _updateConnectionStatus({bool forceReload = false}) async {
    final wasOnline = _isOnline;

    // 1. Check device connectivity
    final connectivityResult = await Connectivity().checkConnectivity();
    final deviceConnected =
        connectivityResult.contains(ConnectivityResult.mobile) ||
        connectivityResult.contains(ConnectivityResult.wifi);

    // 2. If device is connected, check server reachability
    bool serverReachable = false;
    if (deviceConnected) {
      // debugPrint("CHECKING SERVER REACHABILITY");
      serverReachable = true;
      // serverReachable = await _checkServerReachability();
    }

    final isNowOnline = deviceConnected && serverReachable;
    // debugPrint("ONLINE?: ${isNowOnline}");

    if (mounted) {
      setState(() {
        _isOnline = isNowOnline;
      });
    }

    // Se siamo tornati online o è la prima volta, proviamo a caricare i dati (se non ci sono già)
    if (isNowOnline &&
        (wasOnline != isNowOnline || _isCheckingConnection || forceReload)) {
      _loadOnlineData(forceRefresh: forceReload);
    }
  }

  Future<bool> _checkServerReachability() async {
    try {
      return await _tourService.apiService
          .pingServer(timeout: const Duration(seconds: 2))
          .timeout(const Duration(seconds: 2), onTimeout: () => false);
    } catch (_) {
      return false;
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    routeObserver.subscribe(this, ModalRoute.of(context)!);
  }

  @override
  void didPopNext() {
    final currentLanguage = context.locale.languageCode.toLowerCase();
    final currentBaseUrl = _tourService.apiService.getCurrentBaseUrl();

    final shouldForceReload =
        _lastLoadedLanguage != currentLanguage ||
        _lastLoadedBaseUrl != currentBaseUrl;
    _updateConnectionStatus(
      forceReload: shouldForceReload,
    ); // Non forzare il reload, controlla solo connessione
    _loadOfflineTours();
    super.didPopNext();
  }

  @override
  void dispose() {
    routeObserver.unsubscribe(this);
    _connectivitySubscription.cancel();
    super.dispose();
  }

  Future<void> _loadOnlineData({bool forceRefresh = false}) async {
    if (!_isOnline) return;

    final language = context.locale.languageCode.toLowerCase();
    final baseUrl = _tourService.apiService.getCurrentBaseUrl();

    _lastLoadedLanguage = language;
    _lastLoadedBaseUrl = baseUrl;

    // Carica categorie (il provider gestisce il caching se non invalidato)
    if (forceRefresh) {
      ref.refresh(categoriesProvider);
    }

    // Carica tour
    debugPrint(
      "Loading online tours with forceRefresh=$forceRefresh, language=$language",
    );

    unawaited(
      ref
          .read(nearbyToursProvider.notifier)
          .loadTours(forceRefresh: forceRefresh, language: language),
    );

    final position = await _getCurrentPosition().timeout(const Duration(seconds: 2), onTimeout: () => null);

    if (!mounted || position == null) return;
    
    await ref
        .read(nearbyToursProvider.notifier)
        .loadTours(
          forceRefresh: forceRefresh,
          lat: position.latitude,
          lon: position.longitude,
          language: language,
        );
  }

  Future<void> _handleRefresh() async {
    await _updateConnectionStatus(forceReload: true);
    await _loadOfflineTours();
  }

  Future<Position?> _getCurrentPosition() async {
    bool serviceEnabled;
    LocationPermission permission;

    serviceEnabled = await Geolocator.isLocationServiceEnabled();
    if (!serviceEnabled) {
      return null;
    }

    permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
      if (permission == LocationPermission.denied) {
        return null;
      }
    }

    if (permission == LocationPermission.deniedForever) {
      return null;
    }

    return await Geolocator.getCurrentPosition(
      desiredAccuracy: LocationAccuracy.medium,
    );
  }

  Future<void> _loadOfflineTours() async {
    if (_offlineTours.isEmpty && mounted)
      setState(() => _isLoadingOfflineTours = true);
    try {
      final tours = await _offlineService.getOfflineTours();
      if (mounted) setState(() => _offlineTours = tours);
    } catch (e) {
      _showError('error_loading_offline_tours'.tr());
    } finally {
      if (mounted) setState(() => _isLoadingOfflineTours = false);
    }
  }

  void _showError(String message) {
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(message), backgroundColor: Colors.red),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_isCheckingConnection) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    return Scaffold(
      extendBodyBehindAppBar: false,
      appBar: AppBar(
        title: Text(
          "XRTOURGUIDE",
          style: TextStyle(
            fontSize: context.r.sp(24),
            fontWeight: FontWeight.bold,
            fontFamily: "point_panther",
          ),
        ),
        backgroundColor: Colors.white,
        foregroundColor: Colors.black,
        elevation: 0,
        centerTitle: true,
      ),
      body: RefreshIndicator(
        onRefresh: _handleRefresh,
        child:
            _isOnline ? _buildOnlineBody(context) : _buildOfflineBody(context),
      ),
      bottomNavigationBar: BottomNavigationBar(
        items: <BottomNavigationBarItem>[
          BottomNavigationBarItem(
            icon: const Icon(Icons.search),
            label: 'explore_nav'.tr(),
          ),
          BottomNavigationBarItem(
            icon: const Icon(Icons.person_outline),
            label: 'profile_nav'.tr(),
          ),
        ],
        currentIndex: 0,
        selectedItemColor: AppColors.navActive,
        unselectedItemColor: AppColors.navInactive,
        showUnselectedLabels: true,
        onTap: (int index) {
          if (index == 1) {
            Navigator.of(context).push(
              platformPageRoute(
                builder:
                    (context) => UserDetailScreen(
                      isGuest: widget.isGuest,
                      isOffline: !_isOnline,
                    ),
              ),
            );
          }
        },
      ),
    );
  }

  Widget _buildOnlineBody(BuildContext context) {
    return SingleChildScrollView(
      physics: const AlwaysScrollableScrollPhysics(),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _buildHeaderImage(context),
          _buildSearchBar(context),
          _buildOfflineToursSection(context),
          _buildNearbyToursSection(context),
          _buildCategoriesSection(context),
        ],
      ),
    );
  }

  Widget _buildOfflineBody(BuildContext context) {
    return Column(
      children: [
        Container(
          padding: const EdgeInsets.all(16.0),
          color: Colors.amber.withOpacity(0.2),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.wifi_off, color: Colors.black54),
              const SizedBox(width: 8),
              Text(
                'offline_mode_message'.tr(),
                style: const TextStyle(color: Colors.black54),
              ),
            ],
          ),
        ),
        Expanded(
          child: SingleChildScrollView(
            physics:
                const AlwaysScrollableScrollPhysics(), // Importante per il RefreshIndicator
            child: _buildOfflineToursSection(context),
          ),
        ),
      ],
    );
  }

  Widget _buildHeaderImage(BuildContext context) {
    // final screenHeight = MediaQuery.of(context).size.height;
    return Container(
      height: context.r.homeHeaderHeight(),
      decoration: const BoxDecoration(
        image: DecorationImage(
          image: AssetImage('assets/background_app.jpg'),
          fit: BoxFit.cover,
        ),
      ),
      child: Stack(
        children: [
          Positioned.fill(
            child: Container(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    Colors.transparent,
                    AppColors.lightOverlay,
                    AppColors.background,
                  ],
                  stops: const [0.6, 0.8, 1.0],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSearchBar(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20.0, vertical: 10.0),
      child: GestureDetector(
        onTap:
            () => Navigator.of(context).push(
              platformPageRoute(
                builder: (_) => SearchScreen(isGuest: widget.isGuest),
              ),
            ),
        child: Container(
          height: 50,
          decoration: BoxDecoration(
            color: AppColors.searchBarBackground,
            borderRadius: BorderRadius.circular(30.0),
          ),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16.0),
            child: Row(
              children: [
                const Icon(Icons.search, color: AppColors.textSecondary),
                const SizedBox(width: 12),
                Text(
                  'search_bar_hint'.tr(),
                  style: TextStyle(
                    color: AppColors.textSecondary.withOpacity(0.7),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildOfflineToursSection(BuildContext context) {
    if (!_isLoadingOfflineTours && _offlineTours.isEmpty)
      return const SizedBox.shrink();

    final cardHeight = context.r.homeTourCardHeight();
    final cardWidth = context.r.homeTourCardWidth();
    final imageHeight = context.r.homeTourCardImageHeight();

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 10.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(
              horizontal: 20.0,
              vertical: 10.0,
            ),
            child: Text(
              'offline_tours'.tr(),
              style: TextStyle(
                fontSize: context.r.sp(20),
                fontWeight: FontWeight.bold,
                color: AppColors.textPrimary,
              ),
            ),
          ),
          if (_isLoadingOfflineTours)
            SizedBox(
              height: cardHeight,
              child: const Center(child: CircularProgressIndicator()),
            )
          else
            SizedBox(
              height: cardHeight,
              child: ListView.builder(
                scrollDirection: Axis.horizontal,
                itemCount: _offlineTours.length,
                itemBuilder: (context, index) {
                  final tour = _offlineTours[index];
                  return Padding(
                    padding: EdgeInsets.only(
                      left: index == 0 ? 20.0 : 0.0,
                      right: 15.0,
                    ),
                    child: OfflineTourCard(
                      tourData: tour,
                      cardWidth: cardWidth,
                      imageHeight: imageHeight,
                      height: cardHeight,
                      onTap:
                          () => Navigator.push(
                            context,
                            platformPageRoute(
                              builder:
                                  (context) => TourDetailScreen(
                                    tourId: tour['id'],
                                    isGuest: widget.isGuest,
                                    isOffline: true,
                                  ),
                            ),
                          ),
                    ),
                  );
                },
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildNearbyToursSection(BuildContext context) {
    const cardHeight = TravelListItemCard.compactHeight;
    const cardWidth = TravelListItemCard.compactWidth;
    const imageHeight = TravelListItemCard.compactImageHeight;

    // Usa il provider per ottenere lo stato
    final nearbyToursState = ref.watch(nearbyToursProvider);

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 10.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(
              horizontal: 20.0,
              vertical: 10.0,
            ),
            child: Text(
              'recent_tours'.tr(),
              style: TextStyle(
                fontSize: context.r.sp(20),
                fontWeight: FontWeight.bold,
                color: AppColors.textPrimary,
              ),
            ),
          ),
          // if (nearbyToursState.isLoading &&
          //     (nearbyToursState.tours == null ||
          //         nearbyToursState.tours!.isEmpty))
          if (nearbyToursState.isLoading || nearbyToursState.tours == null)
            SizedBox(
              height: cardHeight,
              child: const Center(child: CircularProgressIndicator()),
            )
          else if (nearbyToursState.tours!.isEmpty)
            SizedBox(
              height: cardHeight,
              child: Center(child: Text("no_tours_available".tr())),
            )
          else
            SizedBox(
              height: cardHeight,
              child: ListView.builder(
                scrollDirection: Axis.horizontal,
                itemCount: nearbyToursState.tours?.length ?? 0,
                itemBuilder: (context, index) {
                  final tour = nearbyToursState.tours![index];
                  return Padding(
                    padding: EdgeInsets.only(
                      left: index == 0 ? 20.0 : 0.0,
                      right: 15.0,
                    ),
                    child: TravelListItemCard(
                      tourId: tour.id,
                      imagePath: tour.imagePath,
                      title: tour.title,
                      description: tour.description,
                      cardWidth: cardWidth,
                      imageHeight: imageHeight,
                      height: cardHeight,
                      category: tour.category,
                      rating: tour.rating,
                      reviewCount: tour.reviewCount,
                      totViews: tour.totViews.toString(),
                      creator: tour.creator,
                      lastEdited: tour.lastEdited,
                      onTap: () {
                        unawaited(
                          _analytics.logEvent(
                            name: "tour_open",
                            parameters: {
                              "tour_id": tour.id,
                              "is_guest": widget.isGuest.toString(),
                              "source": "nearby_section",
                            },
                          ),
                        );

                        Navigator.push(
                          context,
                          platformPageRoute(
                            builder:
                                (context) => TourDetailScreen(
                                  tourId: tour.id,
                                  isGuest: widget.isGuest,
                                ),
                          ),
                        );
                      },
                    ),
                  );
                },
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildCategoriesSection(BuildContext context) {
    final screenHeight = MediaQuery.of(context).size.height;
    final screenWidth = MediaQuery.of(context).size.width;

    // Usa il provider per le categorie
    final categoriesAsyncValue = ref.watch(categoriesProvider);

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 10.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(
              horizontal: 20.0,
              vertical: 10.0,
            ),
            child: Text(
              'categories'.tr(),
              style: TextStyle(
                fontSize: context.r.sp(18),
                fontWeight: FontWeight.bold,
                color: AppColors.textPrimary,
              ),
            ),
          ),
          SizedBox(
            height: screenHeight * 0.12,
            child: categoriesAsyncValue.when(
              data:
                  (categories) => ListView.builder(
                    scrollDirection: Axis.horizontal,
                    itemCount: categories.length,
                    itemBuilder: (context, index) {
                      final category = categories[index];
                      return GestureDetector(
                        onTap:
                            () => Navigator.push(
                              context,
                              platformPageRoute(
                                builder:
                                    (context) => CategoryDetailScreen(
                                      isGuest: widget.isGuest,
                                      categoryName: category.name,
                                      tours: const [],
                                    ),
                              ),
                            ),
                        child: Container(
                          width: screenWidth * 0.4,
                          margin: EdgeInsets.only(
                            left: index == 0 ? 20.0 : 0.0,
                            right: 10.0,
                          ),
                          decoration: BoxDecoration(
                            borderRadius: BorderRadius.circular(10.0),
                            image: DecorationImage(
                              image: AssetImage(category.image),
                              fit: BoxFit.cover,
                            ),
                          ),
                          child: Stack(
                            children: [
                              Positioned.fill(
                                child: Container(
                                  decoration: BoxDecoration(
                                    borderRadius: BorderRadius.circular(10.0),
                                    color: AppColors.darkOverlay,
                                  ),
                                ),
                              ),
                              Center(
                                child: Text(
                                  category.name[0].toUpperCase() +
                                      category.name.substring(1).toLowerCase(),
                                  style: TextStyle(
                                    color: Colors.white,
                                    fontWeight: FontWeight.bold,
                                    fontSize: context.r.sp(16),
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                      );
                    },
                  ),
              loading: () => const Center(child: CircularProgressIndicator()),
              error:
                  (err, stack) =>
                      Center(child: Text('Error loading categories')),
            ),
          ),
          const SizedBox(height: 20),
        ],
      ),
    );
  }
}

class OfflineTourCard extends StatefulWidget {
  final Map<String, dynamic> tourData;
  final double cardWidth;
  final double imageHeight;
  final double height;
  final VoidCallback onTap;

  const OfflineTourCard({
    Key? key,
    required this.tourData,
    required this.cardWidth,
    required this.imageHeight,
    required this.height,
    required this.onTap,
  }) : super(key: key);

  @override
  State<OfflineTourCard> createState() => _OfflineTourCardState();
}

class _OfflineTourCardState extends State<OfflineTourCard> {
  String? _imagePath;

  @override
  void initState() {
    super.initState();
    _getImagePath();
  }

  Future<void> _getImagePath() async {
    final appDir = await getApplicationDocumentsDirectory();
    final path =
        '${appDir.path}/offline_tours_data/tour_${widget.tourData['id']}/default_image.jpg';
    if (await File(path).exists()) {
      if (mounted) setState(() => _imagePath = path);
    }
  }

  @override
  Widget build(BuildContext context) {
    final String title = widget.tourData['title'] ?? 'Untitled Tour';
    final String description = widget.tourData['description'] ?? '';

    return GestureDetector(
      onTap: widget.onTap,
      child: SizedBox(
        width: widget.cardWidth,
        height: widget.height,
        child: Card(
          elevation: 2.0,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12.0),
          ),
          margin: const EdgeInsets.only(bottom: 16.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Image
              ClipRRect(
                borderRadius: const BorderRadius.vertical(
                  top: Radius.circular(12.0),
                ),
                child: Container(
                  height: widget.imageHeight,
                  width: double.infinity,
                  color: Colors.grey.shade200,
                  child:
                      _imagePath != null
                          ? ZlibImage(
                            filePath: _imagePath!,
                            // width: widget.cardWidth,
                            // height: widget.imageHeight,
                            fit: BoxFit.cover,
                            errorBuilder:
                                (context, error, stackTrace) => Icon(
                                  Icons.broken_image,
                                  color: Colors.grey.shade400,
                                ),
                          )
                          : Center(
                            child: Icon(
                              Icons.image,
                              color: Colors.grey.shade400,
                            ),
                          ),
                ),
              ),
              // Content
              Padding(
                padding: const EdgeInsets.all(12.0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Title
                    Text(
                      title,
                      style: TextStyle(
                        fontWeight: FontWeight.bold,
                        fontSize: context.r.sp(16),
                        color: AppColors.textPrimary,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    SizedBox(height: context.r.space(8)),
                    // Description
                    Text(
                      description,
                      style: TextStyle(
                        fontSize: context.r.sp(14),
                        color: AppColors.textSecondary,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
