// lib/download_service_web_impl.dart
import 'package:flutter/material.dart';
// ignore: avoid_web_libraries_in_flutter
import 'dart:html' as html; // Only available on web

import 'download_service.dart'; // Import the abstract interface

// Distinct class name for web implementation
class WebDownloadService implements DownloadService {
  @override
  Future<void> downloadFile(
    String url,
    String fileName,
    Function(String, Color) showSnackBar,
  ) async {
    try {
      showSnackBar('Initiating download via browser...', Colors.blue);
      html.AnchorElement anchorElement = html.AnchorElement(href: url);
      anchorElement.download = fileName; // Suggest a filename
      anchorElement
          .click(); // Programmatically click the link to trigger download
      showSnackBar('Download initiated in your browser.', Colors.green);
    } catch (e) {
      showSnackBar('An error occurred during download: $e', Colors.red);
      debugPrint('Download error (Web): $e');
    }
  }
}

// Provide a platform-specific function to get the instance
DownloadService getDownloadServiceForPlatform() => WebDownloadService();
