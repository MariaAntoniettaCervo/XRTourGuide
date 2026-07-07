// lib/download_service_mobile_impl.dart
import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:flutter_downloader/flutter_downloader.dart';
import 'dart:io';
import 'package:device_info_plus/device_info_plus.dart'; // <--- NEW IMPORT

import 'download_service.dart';

class MobileDownloadService implements DownloadService {
  // Private helper method for permission requests
  Future<bool> _ensurePermissionsGranted(
    Function(String, Color) showSnackBar,
  ) async {
    // 1. Request Notification Permission (Mandatory for Android 13+ / API 33+)
    PermissionStatus notificationStatus =
        await Permission.notification.request();
    if (!notificationStatus.isGranted) {
      if (notificationStatus.isPermanentlyDenied) {
        showSnackBar(
          'Notification permission permanently denied. Please enable from app settings.',
          Colors.orange,
        );
        openAppSettings();
      } else {
        showSnackBar(
          'Notification permission denied. Downloads may not work correctly or show progress.',
          Colors.red,
        );
      }
      return false;
    }

    // 2. Handle Storage Permissions based on Android version
    if (Platform.isAndroid) {
      final AndroidDeviceInfo androidInfo =
          await DeviceInfoPlugin().androidInfo;
      final int sdkInt = androidInfo.version.sdkInt;

      if (sdkInt >= 33) {
        // Android 13 (API 33) and above
        // For downloads to public directories, FlutterDownloader generally handles MediaStore APIs
        // which often don't require explicit READ_MEDIA_* permissions for *writing*.
        // However, if your app is reading media or FlutterDownloader has a fallback,
        // it's safer to request these for robust general media interaction.
        // The most critical is Notification, which is already handled above.
        // For saving to Downloads directory, explicit storage permissions are often not needed
        // for apps targeting API 30+ (Scoped Storage).
        // If you were specifically handling *reading* media files, you'd request these:
        // Map<Permission, PermissionStatus> statuses = await [
        //   Permission.photos,
        //   Permission.videos,
        //   Permission.audio,
        // ].request();

        // If you still encounter issues for API 33+ with downloads, consider adding the above block.
        // For now, relying on Notification permission and FlutterDownloader's internal handling
        // for public storage writes is usually sufficient for modern Android.
        debugPrint(
          'Android SDK >= 33. Relying on Scoped Storage/MediaStore for downloads.',
        );
        return true; // Assume success if notification is granted and platform handles storage
      } else if (sdkInt >= 30) {
        // Android 11 (API 30) to Android 12 (API 32)
        // On these versions, WRITE_EXTERNAL_STORAGE is largely deprecated.
        // FlutterDownloader usually uses MediaStore. However, `Permission.storage`
        // might still be checked for general external storage interaction.
        PermissionStatus storageStatus = await Permission.storage.request();
        if (!storageStatus.isGranted) {
          if (storageStatus.isPermanentlyDenied) {
            showSnackBar(
              'Storage permission permanently denied. Please enable from app settings.',
              Colors.orange,
            );
            openAppSettings();
          } else {
            showSnackBar(
              'Storage permission denied (Android 11/12). Cannot download file.',
              Colors.red,
            );
          }
          return false;
        }
      } else {
        // Android 10 (API 29) and below
        // WRITE_EXTERNAL_STORAGE is fully effective here.
        PermissionStatus storageStatus = await Permission.storage.request();
        if (!storageStatus.isGranted) {
          if (storageStatus.isPermanentlyDenied) {
            showSnackBar(
              'Storage permission permanently denied. Please enable from app settings.',
              Colors.orange,
            );
            openAppSettings();
          } else {
            showSnackBar(
              'Storage permission denied (Android 10 and below). Cannot download file.',
              Colors.red,
            );
          }
          return false;
        }
      }
    }
    return true; // All necessary permissions seem to be granted or not needed for current Android version.
  }

  @override
  Future<void> downloadFile(
    String url,
    String fileName,
    Function(String, Color) showSnackBar,
  ) async {
    try {
      // Step 1: Ensure permissions are granted before proceeding
      bool permissionsReady = await _ensurePermissionsGranted(showSnackBar);
      if (!permissionsReady) {
        debugPrint('Permissions not ready. Aborting download.');
        return; // Exit if permissions are not granted
      }

      // Existing logic to get the download directory
      final directory = await getDownloadsDirectory();
      if (directory == null) {
        showSnackBar(
          'Error: Could not determine Downloads directory.',
          Colors.red,
        );
        return;
      }

      showSnackBar('Initiating download...', Colors.blue);

      // Existing FlutterDownloader enqueue logic
      final taskId = await FlutterDownloader.enqueue(
        url: url,
        savedDir: directory.path,
        fileName: fileName,
        showNotification: true,
        openFileFromNotification: true,
        saveInPublicStorage: true,
      );

      if (taskId != null) {
        showSnackBar(
          'Download started. Check notifications for progress.',
          Colors.green,
        );
      } else {
        showSnackBar('Failed to start download.', Colors.red);
      }
    } catch (e) {
      showSnackBar('An error occurred during download: $e', Colors.red);
      debugPrint('Download error (Mobile): $e');
    }
  }
}

// Provide a platform-specific function to get the instance
DownloadService getDownloadServiceForPlatform() => MobileDownloadService();
