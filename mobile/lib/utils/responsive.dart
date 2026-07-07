import 'dart:math';

import 'package:flutter/material.dart';

class AppBreakpoints {
  static const double smallPhone = 360;
  static const double normalPhone = 430;
  static const double tablet = 600;
}

class Responsive {
  final BuildContext context;
  late final MediaQueryData media;
  late final Size size;

  Responsive(this.context) {
    media = MediaQuery.of(context);
    size = media.size;
  }

  double get width => size.width;
  double get height => size.height;

  double get shortestSide => size.shortestSide;
  double get longestSide => size.longestSide;

  bool get isSmallPhone => width < AppBreakpoints.smallPhone;
  bool get isTablet => width >= AppBreakpoints.tablet;

  double get horizontalPadding {
    if (isTablet) return 32;
    if (isSmallPhone) return 14;
    return 20;
  }

  double get maxContentWidth {
    if (isTablet) return 520;
    return double.infinity;
  }

  double clampDoubleValue(double value, double minValue, double maxValue) {
    return value.clamp(minValue, maxValue).toDouble();
  }

  double wp(double percent) => width * percent;
  double hp(double percent) => height * percent;

  double sp(double base) {
    final scale = shortestSide / 390.0;
    return clampDoubleValue(base * scale, base * 0.88, base * 1.18);
  }

  double icon(double base) {
    final scale = shortestSide / 390.0;
    return clampDoubleValue(base * scale, base * 0.85, base * 1.20);
  }

  double space(double base) {
    final scale = shortestSide / 390.0;
    return clampDoubleValue(base * scale, base * 0.80, base * 1.25);
  }

  double buttonHeight() {
    return clampDoubleValue(height * 0.062, 46, 56);
  }

  double roundButtonSize() {
    return clampDoubleValue(shortestSide * 0.13, 48, 64);
  }

  double cameraActionSize() {
    return clampDoubleValue(shortestSide * 0.20, 70, 86);
  }

  double consultationOuterCircleSize() {
    return clampDoubleValue(shortestSide * 0.64, 220, 290);
  }

  double consultationIconRadius() {
    return consultationOuterCircleSize() / 2;
  }

  double consultationIconSize() {
    return clampDoubleValue(shortestSide * 0.2, 60, 82);
  }

  double miniMapWidth() {
    return clampDoubleValue(width * 0.35, 120, 165);
  }

  double cardImageHeight() {
    return clampDoubleValue(height * 0.22, 150, 210);
  }

  double heroImageHeight() {
    return clampDoubleValue(height * 0.36, 240, 320);
  }

  double homeTourCardWidth() {
    return clampDoubleValue(width * 0.62, 220, 285);
  }

  double homeTourCardImageHeight() {
    return clampDoubleValue(height * 0.17, 120, 145);
  }

  double homeTourCardHeight() {
    return homeTourCardImageHeight() + clampDoubleValue(height * 0.13, 96, 120);
  }

  double homeCategoryHeight() {
    return clampDoubleValue(height * 0.12, 86, 110);
  }

  double homeHeaderHeight() {
    return clampDoubleValue(height * 0.25, 180, 240);
  }
}

extension ResponsiveX on BuildContext {
  Responsive get r => Responsive(this);
}
