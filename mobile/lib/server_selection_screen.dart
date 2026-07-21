import 'package:flutter/material.dart';
import 'package:easy_localization/easy_localization.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:xr_tour_guide/home_screen.dart';
import 'package:xr_tour_guide/services/local_state_service.dart';
import 'models/app_colors.dart';
import 'main.dart'; // Importiamo main per accedere a AuthFlowScreen
import 'services/api_service.dart';
import 'services/auth_service.dart';
import 'utils/responsive.dart';
import 'utils/platform_page_route.dart';
import 'providers/home_providers.dart';

class WelcomeScreen extends ConsumerStatefulWidget {
  final bool isGuest;
  final String? initialErrorMessage;

  const WelcomeScreen({
    Key? key,
    required this.isGuest,
    this.initialErrorMessage,
  }) : super(key: key);

  @override
  ConsumerState<WelcomeScreen> createState() => _WelcomeScreenState();
}

class _WelcomeScreenState extends ConsumerState<WelcomeScreen> {
  bool _isLoading = true;
  List<dynamic> _servers = [];
  String? _errorMessage;
  late ApiService _apiService;
  String? _selectionErrorMessage;

  @override
  void initState() {
    super.initState();
    _apiService = ref.read(apiServiceProvider);
    _errorMessage = widget.initialErrorMessage;
    _selectionErrorMessage = widget.initialErrorMessage;
    _fetchServers();
  }

  Future<void> _fetchServers() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });
    const maxAttempts = 3;

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
      try {
        final response = await _apiService.getServersList();
        if (response.statusCode == 200) {
          final servers = response.data as List<dynamic>? ?? [];
          setState(() {
            _servers = servers;
            _isLoading = false;
            _errorMessage =
                servers.isEmpty ? "server_selection_error".tr() : null;
          });
          return;
        }
      } catch (e) {
        debugPrint("Attempt $attempt: Failed to fetch servers - $e");
      }

      if (attempt < maxAttempts) {
        await Future.delayed(
          const Duration(seconds: 1),
        ); // Attendi prima di ritentare
      }
    }

    setState(() {
      _servers = [];
      _isLoading = false;
      _errorMessage = "server_selection_error".tr();
    });
  }

  Future<void> _selectServerAndProceed(String name, String domain) async {
    setState(() {
      _isLoading = true;
      _selectionErrorMessage = null;
    });

    // Imposta il server
    debugPrint("Selected server IP: $domain");
    _apiService.updateBaseUrl(domain);

    final available = await _apiService.pingServer(
      urlToCheck: _apiService.getCurrentBaseUrl(),
      timeout: const Duration(seconds: 1),
    );

    if (!mounted) return;

    if (!available) {
      await ref.read(localStateServiceProvider).clearSelectedServer();

      if (!mounted) return;

      setState(() {
        _isLoading = false;
        _selectionErrorMessage = "server_selection_unavailable".tr();
      });

      return;
    }

    await ref
        .read(localStateServiceProvider)
        .saveSelectedServer(name: name, url: _apiService.getCurrentBaseUrl());

    ref.invalidate(nearbyToursProvider);
    ref.invalidate(categoriesProvider);

    if (!mounted) return;

    Navigator.of(context).pushReplacement(
      platformPageRoute(
        builder: (_) => TravelExplorerScreen(isGuest: widget.isGuest),
      ),
    );
  }

  // Copiato lo stile del pulsante da main.dart per coerenza totale
  Widget _buildPrimaryButton({
    required String text,
    required VoidCallback onPressed,
    required BuildContext context,
    bool isOutlined = false,
  }) {
    final screenWidth = MediaQuery.of(context).size.width;

    return Container(
      width: screenWidth > 600 ? 400 : double.infinity,
      height: 50,
      margin: EdgeInsets.symmetric(
        horizontal: screenWidth > 600 ? (screenWidth - 400) / 2 : 20,
        vertical:
            8, // Ridotto leggermente il margine verticale per raggrupparli
      ),
      child:
          isOutlined
              ? OutlinedButton(
                onPressed: onPressed,
                style: OutlinedButton.styleFrom(
                  side: const BorderSide(color: AppColors.primary),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(25),
                  ),
                  backgroundColor: AppColors.background,
                ),
                child: Text(
                  text,
                  style: TextStyle(
                    color: AppColors.primary,
                    fontSize: context.r.sp(16),
                    fontWeight: FontWeight.w600,
                  ),
                ),
              )
              : ElevatedButton(
                onPressed: onPressed,
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppColors.primary,
                  foregroundColor: Colors.white,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(25),
                  ),
                  elevation: 2,
                  shadowColor: AppColors.cardShadow,
                ),
                child: Text(
                  text,
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: context.r.sp(16),
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
    );
  }

  // @override
  // Widget build(BuildContext context) {
  //   return Scaffold(
  //     backgroundColor: AppColors.background, // Stesso sfondo di main.dart
  //     body: LayoutBuilder(
  //       builder: (context, constraints) {
  //         final screenHeight = constraints.maxHeight;
  //         final screenWidth = constraints.maxWidth;
  //         final isTablet = screenWidth > 600;

  //         return SafeArea(
  //           child: SingleChildScrollView(
  //             child: ConstrainedBox(
  //               constraints: BoxConstraints(
  //                 minHeight: screenHeight - MediaQuery.of(context).padding.top,
  //               ),
  //               child: Column(
  //                 mainAxisAlignment: MainAxisAlignment.center,
  //                 children: [
  //                   // --- SEZIONE TESTO (Simile a onboarding_title) ---
  //                   Padding(
  //                     padding: const EdgeInsets.symmetric(horizontal: 20),
  //                     child: Column(
  //                       children: [
  //                         // Logo o Icona (Opzionale, se vuoi)
  //                         Icon(Icons.travel_explore, size: 80, color: AppColors.primary),
  //                         SizedBox(height: 20),
  //                         // Text(
  //                         //   "XRTOURGUIDE", // O usa una chiave di traduzione se preferisci
  //                         //   style: TextStyle(
  //                         //     fontSize: context.r.sp(28),
  //                         //     fontWeight: FontWeight.bold,
  //                         //     color: AppColors.textPrimary,
  //                         //     letterSpacing: 1.2,
  //                         //   ),
  //                         // ),
  //                         // const SizedBox(height: 16),
  //                         Padding(
  //                           padding: EdgeInsets.symmetric(
  //                             horizontal: isTablet ? 80 : 20,
  //                           ),
  //                           child: Text(
  //                             "server_selection_description".tr(),
  //                             textAlign: TextAlign.center,
  //                             style: TextStyle(
  //                               fontSize: context.r.sp(16),
  //                               color: AppColors.textSecondary,
  //                               height: 1.5,
  //                             ),
  //                           ),
  //                         ),
  //                       ],
  //                     ),
  //                   ),

  //                   SizedBox(height: context.r.space(48)), // Spazio centrale
  //                   // --- SEZIONE PULSANTI ---
  //                   if (_isLoading)
  //                     const CircularProgressIndicator()
  //                   else if (_errorMessage != null || _servers.isEmpty)
  //                     Padding(
  //                       padding: const EdgeInsets.all(16.0),
  //                       child: Column(
  //                         children: [
  //                           Text(
  //                             _errorMessage ?? "server_selection_error".tr(),
  //                             style: const TextStyle(color: Colors.red),
  //                           ),
  //                           ElevatedButton(
  //                             onPressed: _fetchServers,
  //                             child: Text('retry'.tr()),
  //                           ),
  //                         ],
  //                       ),
  //                     )
  //                   else
  //                     ..._servers.map((server) {
  //                       final name = server['name'] ?? 'Unknown Server';
  //                       final domain = server['domain'] ?? '';
  //                       return _buildPrimaryButton(
  //                         text: name,
  //                         context: context,
  //                         isOutlined: false,
  //                         onPressed:
  //                             () => _selectServerAndProceed(context, name, domain),
  //                       );
  //                     }).toList(),
  //                 ],
  //               ),
  //             ),
  //           ),
  //         );
  //       },
  //     ),
  //   );
  // }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      body: LayoutBuilder(
        builder: (context, constraints) {
          final screenHeight = constraints.maxHeight;
          final screenWidth = constraints.maxWidth;
          final isTablet = screenWidth > 600;

          return SafeArea(
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 24),
              child: Column(
                children: [
                  const Spacer(),

                  // Header
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 20),
                    child: Column(
                      children: [
                        Icon(
                          Icons.travel_explore,
                          size: 80,
                          color: AppColors.primary,
                        ),
                        const SizedBox(height: 20),
                        Padding(
                          padding: EdgeInsets.symmetric(
                            horizontal: isTablet ? 80 : 20,
                          ),
                          child: Text(
                            "server_selection_description".tr(),
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              fontSize: context.r.sp(16),
                              color: AppColors.textSecondary,
                              height: 1.5,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),

                  SizedBox(height: context.r.space(32)),

                  // Area server: scrollabile, ma con altezza limitata
                  ConstrainedBox(
                    constraints: BoxConstraints(maxHeight: screenHeight * 0.38),
                    child:
                        _isLoading
                            ? const Center(child: CircularProgressIndicator())
                            : (_errorMessage != null || _servers.isEmpty)
                            ? Padding(
                              padding: const EdgeInsets.all(16.0),
                              child: Column(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Text(
                                    _errorMessage ??
                                        "server_selection_error".tr(),
                                    textAlign: TextAlign.center,
                                    style: const TextStyle(color: Colors.red),
                                  ),
                                  const SizedBox(height: 16),
                                  ElevatedButton(
                                    onPressed: _fetchServers,
                                    child: Text('retry'.tr()),
                                  ),
                                ],
                              ),
                            )
                            : ListView.separated(
                              shrinkWrap: true,
                              padding: const EdgeInsets.only(bottom: 8),
                              itemCount: _servers.length,
                              separatorBuilder:
                                  (_, __) => const SizedBox(height: 4),
                              itemBuilder: (context, index) {
                                final server = _servers[index];
                                final name = server['name'] ?? 'Unknown Server';
                                final domain = server['domain'] ?? '';

                                return _buildPrimaryButton(
                                  text: name,
                                  context: context,
                                  isOutlined: false,
                                  onPressed:
                                      () =>
                                          _selectServerAndProceed(name, domain),
                                );
                              },
                            ),
                  ),

                  const Spacer(),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}
