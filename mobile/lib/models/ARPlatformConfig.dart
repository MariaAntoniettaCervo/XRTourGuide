import 'dart:io';

import 'package:flutter/material.dart';

@immutable
class ARPlatformConfig {
  final double modelScaleCompensation;
  final double totemOffsetY;

  final double gridStartX;
  final double gridStartY;
  final double gridGapX;
  final double gridGapY;

  final double iconScaleTune;
  final double iconOffsetX;
  final double iconOffsetY;
  final double iconOffsetZ;

  final double overlayRadiusFactor;
  final double overlayIconSize;

  const ARPlatformConfig({
    required this.modelScaleCompensation,
    required this.totemOffsetY,
    required this.gridStartX,
    required this.gridStartY,
    required this.gridGapX,
    required this.gridGapY,
    required this.iconScaleTune,
    required this.iconOffsetX,
    required this.iconOffsetY,
    required this.iconOffsetZ,
    required this.overlayRadiusFactor,
    required this.overlayIconSize,
  });
}

const androidARConfig = ARPlatformConfig(
  modelScaleCompensation: 1.0,
  totemOffsetY: 0.0,
  gridStartX: -0.00195,
  gridStartY: 0.0185,
  gridGapX: 0.00635,
  gridGapY: 0.00635,
  iconScaleTune: 0.0,
  iconOffsetX:  0.0,
  iconOffsetY: 0.0,
  iconOffsetZ: 0.0,
  overlayRadiusFactor: 0.28,
  overlayIconSize: 60.0,
);

const iosARConfig = ARPlatformConfig(
  modelScaleCompensation: 1.0,
  totemOffsetY: 0.0,
  gridStartX: -0.00195,
  gridStartY: 0.0185,
  gridGapX: 0.00635,
  gridGapY: 0.00635,
  iconScaleTune: 2.6,
  iconOffsetX: 0.0,
  iconOffsetY: 0.0,
  iconOffsetZ: 0.001,
  overlayRadiusFactor: 0.28,
  overlayIconSize: 70.0,
);


ARPlatformConfig get arPlatformCfg => Platform.isIOS ? iosARConfig : androidARConfig;

