import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:xr_tour_guide/models/tour.dart';
import 'package:xr_tour_guide/models/category.dart';
import 'package:xr_tour_guide/models/waypoint.dart';
import 'package:xr_tour_guide/models/review.dart';
import "package:xr_tour_guide/models/user.dart";
import 'auth_service.dart';
import 'api_service.dart';

final tourServiceProvider = Provider<TourService>((ref) {
  final apiService = ref.read(apiServiceProvider);
  return TourService(apiService);
});

class TourService {
  // Instance of ApiService to handle API calls
  final ApiService apiService;
  TourService(this.apiService);

  Future<List<Tour>> getNearbyTours(int timeout, double latitude, double longitude, {String? language}) async {
    try {
      final response = await apiService.getNearbyTours(timeout, latitude, longitude, baseUrl: apiService.getCurrentBaseUrl(), language: language);
      if (response.statusCode == 200) {
        final data = response.data as List;
        return data.map((tour) => Tour.fromJson(tour)).toList();
      } else {
        throw Exception('Failed to load tours');
      }
    } catch (e) {
      debugPrint("Nearby Tours Retrieval error: $e");
      rethrow;
    }
  }

    Future<List<Tour>> getAllNearbyTours(int timeout, {String? language, int? limit}) async {
    try {
      final response = await apiService.getAllNearbyTours(timeout, baseUrl: apiService.getCurrentBaseUrl(), language: language, limit:limit);
      if (response.statusCode == 200) {
        final data = response.data as List;
        return data.map((tour) => Tour.fromJson(tour)).toList();
      } else {
        throw Exception('Failed to load tours');
      }
    } catch (e) {
      debugPrint("Nearby Tours Retrieval error: $e");
      rethrow;
    }
  }


    Future<Tour> getTourById(int tourId) async {
      try {
        final response = await apiService.getTourDetails(tourId, baseUrl: apiService.getCurrentBaseUrl());
        if (response.statusCode == 200) {
          final data = response.data;
          return Tour.fromJson(data);
        } else {
          throw Exception('Failed to load tour details');
        }
      } catch (e) {
        debugPrint("Tour Details Retrieval error: $e");
        rethrow;
      }
  }

  Future<List<Tour>> getToursByCategory(String category, {String? language}) async {
    try {
      final response = await apiService.getTourByCategory(category, baseUrl: apiService.getCurrentBaseUrl(), language: language);
      if (response.statusCode == 200) {
        final data = response.data as List;
        return data.map((tour) => Tour.fromJson(tour)).toList();
      } else {
        throw Exception('Failed to load tours');
      }
    } catch (e) {
      debugPrint("Tours By category Retrieval error: $e");
      rethrow;
    }
  }

  Future<List<Tour>> getToursBySearchTerm(String searchTerm, {String? language}) async {
    try {
      final response = await apiService.getTourBySearchTerm(
        searchTerm.toLowerCase(),
        baseUrl: apiService.getCurrentBaseUrl(),
        language: language,
      );
      if (response.statusCode == 200) {
        final data = response.data as List;
        return data.map((tour) => Tour.fromJson(tour)).toList();
      } else {
        throw Exception('Failed to load tours');
      }
    } catch (e) {
      debugPrint("Nearby Tours Retrieval error: $e");
      rethrow;
    }
  }

Future<List<Waypoint>> getWaypointsByTour(int tourId) async {
    try {
      final response = await apiService.getTourWaypoints(tourId, baseUrl: apiService.getCurrentBaseUrl());
      if (response.statusCode == 200) {
        final data = response.data;
        final waypointData = data["waypoints"] as List;

        // Waypoints principali del tour
        List<Waypoint> allWaypoints =
            waypointData
                .map((waypoint) => Waypoint.fromJson(waypoint))
                .toList()
                ..sort(Waypoint.compareByPosition);

        // Se ci sono sub-tours, aggiungi i loro waypoints come sub-waypoints
        if (data.containsKey('sub_tours') && data['sub_tours'] != null) {
          final subTours = data['sub_tours'] as List;

          for (var subTour in subTours) {
            final subWaypointData = subTour['waypoints'] as List;
            final subWaypoints =
                subWaypointData
                    .map((waypoint) => Waypoint.fromJson(waypoint))
                    .toList()
                    ..sort(Waypoint.compareByPosition);

            // Crea un waypoint principale per il sub-tour
            final subTourInfo = subTour['sub_tour'];
            final subTourWaypoint = Waypoint(
              id: subTourInfo['id'],
              title: subTourInfo['title'],
              subtitle: subTourInfo['description'] ?? '',
              description: subTourInfo['description'] ?? '',
              latitude: subTourInfo['lat']?.toDouble() ?? 0.0,
              longitude: subTourInfo['lon']?.toDouble() ?? 0.0,
              images: [], // Sub-tour principale non ha immagini
              category: subTourInfo['category'] ?? 'MIXED',
              position: (subTourInfo["position"] as num?)?.toInt() ?? 999999,
              subWaypoints: subWaypoints, // Aggiungi i sub-waypoints qui
            );

            allWaypoints.add(subTourWaypoint);
          }
        }

        allWaypoints.sort(Waypoint.compareByPosition);
        return allWaypoints;
      } else {
        throw Exception('Failed to load tour waypoints');
      }
    } catch (e) {
      debugPrint("Tour Waypoints Retrieval error: $e");
      rethrow;
    }
  }
  Future<List<Review>> getReviewByTour({int? tourId, int? userId, required int max}) async {
    List<Review> reviews = [];
    try {
      final response = await apiService.getTourReviews(tourId!, baseUrl: apiService.getCurrentBaseUrl());
      if (response.statusCode == 200) {
        final data = response.data as List;
        reviews = data.map((review) => Review.fromJson(review)).toList();
      } else {
        throw Exception('Failed to load tour reviews');
      }     
    } catch (e) {
      debugPrint("Tour Reviews Retrieval error: $e");
      rethrow; 
    }

    // Return only the first 'max' reviews
    if (max > reviews.length) {
      max = reviews.length; // Adjust max to the length of the list if out of bounds
    }
    if (max < 0) {
      max = 0; // Ensure max is not negative
    }
    if (max == 0) {
      //return all reviews if max is 0
      return reviews.toList();
    } else {
      return reviews.take(max).toList();
    }
  }

  // Simulate API call to get categories
  Future<List<Category>> getCategories() async {
    // Simulate network delay
    await Future.delayed(const Duration(milliseconds: 500));

    // Mock data
    return [
      Category(name: 'INDOOR', image: 'assets/interior.jpg'),
      Category(name: 'OUTDOOR', image: 'assets/exterior.jpg'),
      Category(name: 'MIXED', image: 'assets/int-exterior.jpg'),
      Category(name: "GUIDE", image: 'assets/things.png'),
    ];
  }

Future<User> getUserDetails() async {
  try {
    final response = await apiService.getProfileDetails();
    if (response.statusCode == 200) {
      final data = response.data;
      return User(
        id: data['id'],
        name: data['first_name'] ?? '',
        surname: data['last_name'] ?? '',
        mail: data['email']?? '',
        city: data['city'] ?? '',
        token: "abc",
        description: data['description'] ?? '',
        reviewCount: data['reviewCount'] ?? 0,
      );
    } else {
      throw Exception('Failed to load user details');
    }
  } catch (e) {
    debugPrint("User Details Retrieval error: $e");
    rethrow;
  }
}

  Future<({List<Review> reviews, int totalCount})> getReviewByUser(int max) async {
    List<Review> reviews = [];
    int totalCount = 0;
    try {
      final response = await apiService.getUserReviews(baseUrl: apiService.getCurrentBaseUrl());
      if (response.statusCode == 200) {
        //Dizionario con reviews (lista) e review_count (intero)
        final data = response.data;
        final reviews_raw = data['reviews'] as List;
        totalCount = data['review_count'] as int? ?? 0;
        reviews = reviews_raw.map((review) => Review.fromJson(review)).toList();
      } else {
        throw Exception('Failed to load user reviews');
      }
    } catch (e) {
      debugPrint("User Reviews Retrieval error: $e");
      rethrow;
    }

    // Return only the first 'max' reviews
    if (max > reviews.length) {
      max =
          reviews
              .length; // Adjust max to the length of the list if out of bounds
    }
    if (max < 0) {
      max = 0; // Ensure max is not negative
    }

    List<Review> finalReviews;

    if (max == 0) {
      //return all reviews if max is 0
      finalReviews = reviews.toList();
    } else {
      finalReviews = reviews.take(max).toList();
    }

    return (reviews: finalReviews, totalCount: totalCount);
  }

  Future<bool> hasUserReviewedTour(int tourId) async {
    final response = await apiService.hasReviewedTour(
      tourId,
      baseUrl: apiService.getCurrentBaseUrl(),
    );

    if (response.statusCode == 200) {
      final data = response.data as Map<String, dynamic>;
      return data['has_reviewed'] == true;
    }
    throw Exception('Failed to check review status');
  }

  Future<Map<String, dynamic>> getResourceByWaypointAndType(int waypointId, String type) async {
    Map<String, dynamic> resource = {};
    try {
      final response = await apiService.loadResource(waypointId, type, baseUrl: apiService.getCurrentBaseUrl());
      if (response.statusCode == 200) {
        resource = response.data as Map<String, dynamic>;
      } else {
        throw Exception('Failed to load resource of type $type for waypoint $waypointId');
      }
    } catch (e) {
      debugPrint("Resource Retrieval error: $e");
      rethrow;
    }
    return resource;
  }
}
