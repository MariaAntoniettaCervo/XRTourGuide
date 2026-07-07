import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:firebase_analytics/firebase_analytics.dart';

final firebaseAnalyticsProvider = Provider<FirebaseAnalytics>((ref) {
  return FirebaseAnalytics.instance;
});

final analyticsServiceProvider = Provider<AnalyticsService>((ref) {
  final firebaseAnalytics = ref.watch(firebaseAnalyticsProvider);
  return AnalyticsService(firebaseAnalytics);
});

class AnalyticsService {
  AnalyticsService(this._analytics);
  final FirebaseAnalytics _analytics;

  Future<void> _safe(Future<void> Function() action) async {
    try {
      await action();
    } catch (e) {
      debugPrint('Analytics error: $e');
    }
  }

  Future<void> logEvent({
    required String name,
    Map<String, Object?>? parameters,
  }) async {
    final cleaned = <String, Object>{};
    parameters?.forEach((k, v) {
      if (v == null) return;
      
      if (v is String || v is num) {
        cleaned[k] = v;
      } else {
        cleaned[k] = v.toString();
      }
    });
    debugPrint("""Logging event: $name with parameters: $cleaned""");
    await _safe(() => _analytics.logEvent(name: name, parameters: cleaned));
  }

  Future<void> screenView(String screenName) async {
    await _safe(() => _analytics.logScreenView(screenName: screenName));
  }

  Future<void> setUserId(String? userId) async {
    await _safe(() => _analytics.setUserId(id: userId));
  }

  Future<void> appError({
    required String feature,
    required String action,
    required Object error,
  }) async {
    await logEvent(
      name: 'app_error',
      parameters: {
        'feature': feature,
        'action': action,
        'error_type': error.runtimeType.toString(),
      },
    );
  }

}