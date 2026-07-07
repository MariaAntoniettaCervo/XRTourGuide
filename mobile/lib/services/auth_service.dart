import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'secure_storage_service.dart';
import 'package:dio/dio.dart';
import 'api_service.dart';
import 'analytics_service.dart';
import 'package:google_sign_in/google_sign_in.dart';
import 'package:sign_in_with_apple/sign_in_with_apple.dart';

enum AuthStatus { authenticated, unauthenticated, loading, registering }

final authServiceProvider = ChangeNotifierProvider<AuthService>((ref) {
  return AuthService(ref);
});

final apiServiceProvider = Provider<ApiService>((ref) {
  return ApiService(ref);
});

const String googleIosClientId = String.fromEnvironment("GOOGLE_IOS_CLIENT_ID", defaultValue: "");
const String googleWebClientId = String.fromEnvironment("GOOGLE_WEB_CLIENT_ID", defaultValue: "");


class AuthService extends ChangeNotifier {
  final Ref ref;
  late final ApiService apiService;
  late final AnalyticsService _analytics;
  final SecureStorageService _storageService = SecureStorageService();
  final GoogleSignIn _googleSignIn = GoogleSignIn.instance;
  bool _googleInitialized = false;
  AuthStatus _authStatus = AuthStatus.loading;
  AuthStatus get authStatus => _authStatus;

  String? _loginErrorMessage;
  String? get loginErrorMessage=> _loginErrorMessage;


  AuthService(this.ref) {
    apiService = ref.read(apiServiceProvider);
    _analytics = ref.read(analyticsServiceProvider);
    _checkAuthStatus();
  }


  Future<void> _checkAuthStatus() async {
    _authStatus = AuthStatus.loading;
    notifyListeners();

    final accessToken = await _storageService.getAccessToken();
    final refreshToken = await _storageService.getRefreshToken();

    final serverUp = await apiService.pingServer(timeout: const Duration(seconds: 2));

    if (serverUp) {
      if (refreshToken != null) {
        final refreshed = await _refreshAccessTokenSilently(timeout: const Duration(seconds: 5));
        if (refreshed) {
          _authStatus = AuthStatus.authenticated;
        } else {
          await _storageService.deleteAllTokens();
          _authStatus = AuthStatus.unauthenticated;
        }
      } else {
        _authStatus = AuthStatus.unauthenticated;
      }
    } else {
      if (accessToken != null) {
        _authStatus = AuthStatus.authenticated;
      } else {
        _authStatus = AuthStatus.unauthenticated;
      }
    }
    notifyListeners();

    // [LOGGER] Log the auth status check event
    await _analytics.logEvent(
      name: "auth_status_resolved",
      parameters: {
        'status' : _authStatus.name,
        'server_up': serverUp,
      },
    );
  }

  Future<bool> _refreshAccessTokenSilently({Duration timeout = const Duration(seconds: 4)}) async{
    try{
      final refreshToken = await _storageService.getRefreshToken();
      if (refreshToken == null) return false;

      final response = await apiService.dio.post(
        '/api/token/refresh/',
        data: {"refresh": refreshToken},
        options: Options(
          validateStatus: (s) => s == 200 || s == 401,
          sendTimeout: timeout,
          receiveTimeout: timeout,
        ),
      );

      if (response.statusCode == 200){
        final newAccess = response.data["access"] as String?;
        if (newAccess == null) return false;
        await _storageService.saveTokens(accessToken: newAccess, refreshToken: refreshToken);
        return true;
      }
      return false;
    }catch (e) {
      return false;
    }
  }

  Future<void> login(String email, String password) async {
    // _authStatus = AuthStatus.loading;
    // notifyListeners();

    try {
      final response = await apiService.login(email, password);
      if (response.statusCode == 401) {
        // _authStatus = AuthStatus.unauthenticated;
        _loginErrorMessage = "Email or password is incorrect";
        // notifyListeners();
        throw Exception(_loginErrorMessage);
      }

      final accessToken = response.data['access'];
      final refreshToken = response.data['refresh'];

      int userId = response.data['user']["id"];

      await _storageService.saveTokens(
        accessToken: accessToken,
        refreshToken: refreshToken,
      );
      _authStatus = AuthStatus.authenticated;
      _analytics.setUserId(userId.toString());
      notifyListeners();
    } catch (e) {
      debugPrint("Login Error: $e");
      // _authStatus = AuthStatus.unauthenticated;
      _loginErrorMessage ??= "An error occurred during login. Please try again.";
      // notifyListeners();
      rethrow;
    }
  }

  Future<void> register(String username, String password, String name, String surname, String mail, String description, String city) async {
    _authStatus = AuthStatus.loading;
    notifyListeners();

    try {
      // final response = await dio.post('/register/',
      //  data: {'username': username, 'password': password, 'first_name': name, 'last_name': surname, 'email': mail, 'description': description, 'city': city});
      await apiService.register(
        username,
        password,
        name,
        surname,
        mail,
        description,
        city,
      );

      _authStatus = AuthStatus.registering;
    } catch (e) {
      _authStatus = AuthStatus.unauthenticated;
    }
    notifyListeners();
  }

  Future<void> deleteAccount(
    String password,
  ) async {

    try {
      await apiService.deleteAccount(
        password,
      );
      _authStatus = AuthStatus.unauthenticated;
    } catch (e) {
      debugPrint("Delete account error: $e");
      _authStatus = AuthStatus.authenticated;
    }
    notifyListeners();
  }

  Future<void> updatePassword(String oldPassword, String newPassword) async {
    try {
      await apiService.updatePassword(oldPassword, newPassword);
    } catch (e) {
      debugPrint("Change Password error: $e");
    }
  }

  Future<void> updateAccount(String firstName, String lastName, String mail, String description) async {
    try {
      await apiService.updateAccount(
        firstName,
        lastName,
        mail,
        description,
      );
    } catch (e) {
      debugPrint("Update Account error: $e");
    }
  }

  Future<Response> resetPassword(String email) async {
    try {
      final response = await apiService.resetPassword(email);
      return response;
      // Handle response if needed
    } catch (e) {
      debugPrint("Reset Password error: $e");
      rethrow;
    }
  }


  Future<void> logout() async {
    debugPrint("Logout Called");
    _authStatus = AuthStatus.loading;
    notifyListeners();

    try {
      await _ensureGoogleInitialized();
      await _googleSignIn.signOut();
    } catch (_) {}

    await _storageService.deleteAllTokens();
    _authStatus = AuthStatus.unauthenticated;

    _analytics.setUserId(null);
    notifyListeners();
  }

  Future<void> _ensureGoogleInitialized() async {
    debugPrint(googleWebClientId);
    if (_googleInitialized) return;

    await _googleSignIn.initialize(
      clientId: (Platform.isIOS && googleIosClientId.isNotEmpty) ? googleIosClientId : null,
      serverClientId: googleWebClientId.isNotEmpty ? googleWebClientId : null,
    );
    _googleInitialized = true;
  }

  Future<void> loginWithGoogle() async {
    try {
      await _ensureGoogleInitialized();

      final GoogleSignInAccount googleUser = await _googleSignIn.authenticate();

      final GoogleSignInAuthentication googleAuth = googleUser.authentication;

      final String? idToken = googleAuth.idToken;
      if (idToken == null || idToken.isEmpty) {
        throw Exception("Missing Google ID token");
      }

      final response = await apiService.googleMobileLogin(idToken);

      final accessToken = response.data['access'];
      final refreshToken = response.data['refresh'];
      final int userId = response.data['user']["id"];

      await _storageService.saveTokens(
        accessToken: accessToken,
        refreshToken: refreshToken,
      );

      _authStatus = AuthStatus.authenticated;
      _analytics.setUserId(userId.toString());
      notifyListeners();
    } catch (e) {
      debugPrint("Google Login Error: $e");
      rethrow;
    }
  }

  Future<void> loginWithApple() async {
    try {
      final credential = await SignInWithApple.getAppleIDCredential(
        scopes: [
          AppleIDAuthorizationScopes.email,
          AppleIDAuthorizationScopes.fullName,
        ],
      );

      final identityToken = credential.identityToken;
      final authorizationCode = credential.authorizationCode;

      if (identityToken == null || identityToken.isEmpty) {
        throw Exception("Missing Apple identity token");
      }

      if (authorizationCode.isEmpty) {
        throw Exception("Missing Apple authorization code");
      }

      final response = await apiService.appleMobileLogin(
        identityToken: identityToken,
        authorizationCode: authorizationCode,
        givenName: credential.givenName,
        familyName: credential.familyName,
        email: credential.email,
      );

      final accessToken = response.data['access'];
      final refreshToken = response.data['refresh'];
      final int userId = response.data['user']["id"];

      await _storageService.saveTokens(
        accessToken: accessToken,
        refreshToken: refreshToken
      );

      _authStatus = AuthStatus.authenticated;
      _analytics.setUserId(userId.toString());
      notifyListeners();
    } catch (e) {
      debugPrint("Apple Login Error: $e");
      rethrow;
    }
  }
}
