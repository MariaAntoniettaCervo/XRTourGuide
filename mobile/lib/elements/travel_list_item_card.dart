import 'package:flutter/material.dart';
import '../models/app_colors.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../services/auth_service.dart';
import '../services/local_state_service.dart';
import '../utils/responsive.dart';
import 'zlib_image.dart';
import 'package:cached_network_image/cached_network_image.dart';


class TravelListItemCard extends ConsumerWidget {
  final String imagePath; // Path to the image asset
  final String title; // The title of the item
  final String description; // A short description of the item
  final double cardWidth; // The width of the card
  final VoidCallback? onTap; // Optional callback for when the card is tapped
  final double? height; // Optional height for the card
  final double? imageHeight; // Optional height for the image
  final bool fullWidth; // Whether the card should take full width
  final String? category; // Optional category text
  final double? rating; // Optional rating value
  final int? reviewCount; // Optional review count
  // final bool isFavorite; // Whether to show as favorite
  final String? creator;
  final String? lastEdited;
  final String? totViews;
  final int? tourId;

  static const double compactWidth = 250;
  static const double compactHeight = 252;
  static const double compactImageHeight = 132;
  static const double fullImageHeight = 180;


  const TravelListItemCard({
    Key? key,
    required this.tourId,
    required this.imagePath,
    required this.title,
    required this.description,
    required this.cardWidth,
    this.onTap,
    this.height,
    this.imageHeight,
    this.fullWidth = false,
    this.category,
    this.rating,
    this.reviewCount,
    this.creator,
    this.lastEdited,
    this.totViews,
    // this.isFavorite = false,
  }) : super(key: key);

@override
  Widget build(BuildContext context, WidgetRef ref) {
    final localStateService = ref.read(localStateServiceProvider);
    final apiService = ref.read(apiServiceProvider);

    final bool isCompact = !fullWidth;

    final double effectiveWidth =
        fullWidth
            ? double.infinity
            : (cardWidth > 0 ? cardWidth : compactWidth);

    final double? effectiveHeight =
        height ?? (isCompact ? compactHeight : null);

    final double effectiveImageHeight =
        imageHeight ?? (isCompact ? compactImageHeight : fullImageHeight);

    return FutureBuilder<bool>(
      future: localStateService.isTourCompleted(tourId!),
      builder: (context, snapshot) {
        final bool isCompleted = snapshot.data ?? false;

        final image = Stack(
          children: [
            ClipRRect(
              borderRadius: const BorderRadius.vertical(
                top: Radius.circular(10),
              ),
              child: CachedNetworkImage(
                imageUrl:
                    "${apiService.getCurrentBaseUrl()}/stream_minio_resource/?tour=$tourId",
                width: double.infinity,
                height: effectiveImageHeight,
                fit: BoxFit.cover,
                memCacheWidth: 900,
                maxWidthDiskCache: 1200,
                placeholder:
                    (context, url) => const SizedBox(
                      height: 132,
                      child: Center(
                        child: CircularProgressIndicator(strokeWidth: 2),
                      ),
                    ),
                errorWidget:
                    (context, url, error) => Container(
                      height: effectiveImageHeight,
                      color: Colors.grey.shade200,
                      child: const Center(
                        child: Icon(Icons.broken_image, color: Colors.grey),
                      ),
                    ),
              ),
            ),
            if (isCompleted)
              Positioned(
                top: 10,
                right: 10,
                child: Container(
                  padding: const EdgeInsets.all(6),
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
                  child: const Icon(Icons.check, color: Colors.white, size: 16),
                ),
              ),
          ],
        );

        final content = Padding(
          padding: const EdgeInsets.fromLTRB(10, 8, 10, 8),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize:
                effectiveHeight == null ? MainAxisSize.min : MainAxisSize.max,
            children: [
              if (category != null || rating != null)
                SizedBox(
                  height: 20,
                  child: Row(
                    children: [
                      if (category != null)
                        Expanded(
                          child: Text(
                            category!,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              fontSize: 12,
                              color: AppColors.textSecondary,
                            ),
                          ),
                        ),
                      if (rating != null)
                        Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Icon(
                              Icons.star,
                              color: Colors.amber,
                              size: 15,
                            ),
                            const SizedBox(width: 3),
                            Text(
                              rating!.toStringAsFixed(1),
                              style: const TextStyle(
                                fontWeight: FontWeight.bold,
                                fontSize: 12,
                                color: AppColors.textPrimary,
                              ),
                            ),
                            if (totViews != null) ...[
                              const SizedBox(width: 6),
                              const Icon(
                                Icons.remove_red_eye,
                                size: 14,
                                color: AppColors.textSecondary,
                              ),
                              const SizedBox(width: 3),
                              Text(
                                totViews ?? "0",
                                style: const TextStyle(
                                  fontSize: 12,
                                  fontWeight: FontWeight.bold,
                                  color: AppColors.textSecondary,
                                ),
                              ),
                            ],
                          ],
                        ),
                    ],
                  ),
                ),

              if (category != null || rating != null) const SizedBox(height: 5),

              Text(
                title,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.bold,
                  color: AppColors.textPrimary,
                ),
              ),

              const SizedBox(height: 4),

              Text(
                description,
                maxLines: isCompact ? 2 : 3,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  fontSize: 13,
                  height: 1.25,
                  color: AppColors.textSecondary,
                ),
              ),
            ],
          ),
        );

        return GestureDetector(
          onTap: onTap,
          child: SizedBox(
            width: effectiveWidth,
            height: effectiveHeight,
            child: Card(
              margin: const EdgeInsets.only(bottom: 8),
              elevation: 3,
              clipBehavior: Clip.antiAlias,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(10),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  image,
                  if (effectiveHeight == null)
                    content
                  else
                    Expanded(child: content),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}
