import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:xr_tour_guide/models/tour.dart';
import 'models/app_colors.dart';
import 'elements/travel_list_item_card.dart';
import 'tour_details_page.dart';
import 'services/tour_service.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import "package:easy_localization/easy_localization.dart";
import 'services/analytics_service.dart';
import 'utils/responsive.dart';
import 'utils/platform_page_route.dart';



class CategoryDetailScreen extends ConsumerStatefulWidget {
  final String categoryName;
  final List<Tour> tours;
  final bool isGuest;

  const CategoryDetailScreen({
    Key? key,
    required this.categoryName,
    required this.tours,
    required this.isGuest,
  }) : super(key: key);

  @override
  ConsumerState<CategoryDetailScreen> createState() => _CategoryDetailScreenState();
}

class _CategoryDetailScreenState extends ConsumerState<CategoryDetailScreen> {

  late TourService _tourService;
  late AnalyticsService _analytics;

  List<Tour>? _categoriesTour;
  bool _isLoading = true;

  void initState() {
    super.initState();
    _tourService = ref.read(tourServiceProvider);
    _analytics = ref.read(analyticsServiceProvider);
    _loadData();
  }

  Future<void> _loadData() async {
    // Load all data in parallel
    await Future.wait([
      _loadCategoryTours(),
    ]);
  }

  Future<void> _loadCategoryTours() async {
    try {
      final language = context.locale.languageCode.toLowerCase();
      final tours = await _tourService.getToursByCategory(widget.categoryName, language: language);
      if (mounted) {
        setState(() {
          _categoriesTour = tours;
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
        _showError('error_loading_tours'.tr());
      }
    }
  }

  void _showError(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), backgroundColor: Colors.red),
    );
  }




  @override
  Widget build(BuildContext context) {
    final screenWidth = MediaQuery.of(context).size.width;

    if (_isLoading) {
      return const Scaffold(
        body: Center(
          child: CircularProgressIndicator(),
        ),
      );
    }

    return Scaffold(
      extendBodyBehindAppBar: true,
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: Colors.black),
          onPressed: () => Navigator.of(context).pop(),
        ),
        systemOverlayStyle: const SystemUiOverlayStyle(
          statusBarColor: Colors.transparent,
          statusBarIconBrightness: Brightness.dark,
        ),
      ),
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Add some space at the top for the status bar and app bar
          SizedBox(height: MediaQuery.of(context).padding.top + 56),

          // Category title and results count
          Padding(
            padding: const EdgeInsets.symmetric(
              horizontal: 20.0,
              vertical: 10.0,
            ),
            child: Text(
              'category_results'.tr(namedArgs: {'category': widget.categoryName, 'count': '${_categoriesTour?.length ?? 0}'}),
              style: TextStyle(
                fontSize: context.r.sp(24),
                fontWeight: FontWeight.bold,
                color: AppColors.textPrimary,
              ),
            ),
          ),

          // List of tours
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.symmetric(horizontal: 20.0),
              itemCount: _categoriesTour?.length,
              itemBuilder: (context, index) {
                final tour = _categoriesTour![index];
                return TravelListItemCard(
                  tourId: tour.id,
                  imagePath: tour.imagePath,
                  title: tour.title,
                  description: tour.description,
                  cardWidth: double.infinity, // Full width minus padding
                  fullWidth: true,
                  imageHeight: context.r.cardImageHeight(),
                  category: tour.category,
                  rating: tour.rating,
                  reviewCount: tour.reviewCount,
                  totViews: tour.totViews.toString(),
                  // isFavorite: tour['isFavorite'] ?? false,
                  onTap:
                      () {
                        unawaited(
                          _analytics.logEvent(
                            name: "tour_open",
                            parameters: {
                              "tour_id": tour.id,
                              "is_guest": widget.isGuest.toString(),
                              "source": "categories_list",
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
                      }
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}
