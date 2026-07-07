import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/tour.dart';
import '../models/category.dart';
import '../services/tour_service.dart';

// Stato per i tour vicini
class NearbyToursState {
  final List<Tour>? tours;
  final bool isLoading;
  final DateTime? lastUpdated;
  final String? language;

  NearbyToursState({this.tours, this.isLoading = false, this.lastUpdated, this.language});

  NearbyToursState copyWith({
    List<Tour>? tours,
    bool? isLoading,
    DateTime? lastUpdated,
    String? language,
  }) {
    return NearbyToursState(
      tours: tours ?? this.tours,
      isLoading: isLoading ?? this.isLoading,
      lastUpdated: lastUpdated ?? this.lastUpdated,
      language: language ?? this.language,
    );
  }
}

class NearbyToursNotifier extends StateNotifier<NearbyToursState> {
  final TourService _tourService;

  NearbyToursNotifier(this._tourService)
    : super(NearbyToursState(isLoading: true));

  Future<void> loadTours({
    bool forceRefresh = false,
    double? lat,
    double? lon,
    String? language,
  }) async {
    debugPrint(
      "loadTours called with forceRefresh=$forceRefresh, lat=$lat, lon=$lon",
    );
    // Se abbiamo già i dati e non è un refresh forzato, non fare nulla
    if (!forceRefresh && state.tours != null && state.tours!.isNotEmpty && state.language == language) {
      debugPrint("Using cached tours data");
      return;
    }

    state = state.copyWith(isLoading: true);

    try {
      List<Tour> tours;
      if (lat != null && lon != null) {
        debugPrint("Loading tours for location: ($lat, $lon)");
        tours = await _tourService.getNearbyTours(0, lat, lon, language: language);
      } else {
        debugPrint("Loading tours without location");
        tours = await _tourService.getAllNearbyTours(0, language: language);
      }
      state = state.copyWith(
        tours: tours,
        isLoading: false,
        lastUpdated: DateTime.now(),
        language: language,
      );
    } catch (e) {
      state = state.copyWith(isLoading: false);
      debugPrint("Error loading tours: $e");
    }
  }
}

final nearbyToursProvider =
    StateNotifierProvider<NearbyToursNotifier, NearbyToursState>((ref) {
      final tourService = ref.watch(tourServiceProvider);
      return NearbyToursNotifier(tourService);
    });

// Provider per le categorie (usiamo FutureProvider ma con keepAlive per caching semplice)
final categoriesProvider = FutureProvider<List<Category>>((ref) async {
  final tourService = ref.watch(tourServiceProvider);
  return tourService.getCategories();
});
