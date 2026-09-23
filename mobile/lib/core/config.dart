import 'package:flutter/foundation.dart';

/// Adresse de l'API, fixée à la compilation :
/// `flutter run --dart-define=API_URL=https://api.ludifun.fr`.
///
/// Par défaut : l'hôte de l'émulateur Android (10.0.2.2), `localhost` sur iOS et
/// l'origine de la page en web (l'API et l'application servies ensemble).
const _apiUrlOverride = String.fromEnvironment('API_URL');

String apiBaseUrl() {
  if (_apiUrlOverride.isNotEmpty) return _apiUrlOverride;
  if (kIsWeb) return Uri.base.origin;
  return defaultTargetPlatform == TargetPlatform.android
      ? 'http://10.0.2.2:8000'
      : 'http://localhost:8000';
}
