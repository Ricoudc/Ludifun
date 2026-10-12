import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

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

/// Versions de test (debug) : l'adresse du serveur se choisit sur l'écran de premier
/// lancement, pour essayer l'application sur un vrai téléphone relié à l'ordinateur qui
/// fait tourner l'API. Absent des versions publiées.
const serverSettingsEnabled = !kReleaseMode;

const _serverKey = 'ludifun.api_url';

Future<String?> readSavedApiUrl([
  FlutterSecureStorage storage = const FlutterSecureStorage(),
]) async {
  try {
    return await storage.read(key: _serverKey);
  } on Exception {
    return null;
  }
}

Future<void> saveApiUrl(
  String url, [
  FlutterSecureStorage storage = const FlutterSecureStorage(),
]) => storage.write(key: _serverKey, value: url);

/// « 192.168.1.20:8000 » → « http://192.168.1.20:8000 » ; `null` si l'adresse est illisible.
String? normalizeApiUrl(String input) {
  var text = input.trim();
  if (text.isEmpty) return null;
  if (!text.contains('://')) text = 'http://$text';
  final uri = Uri.tryParse(text);
  if (uri == null || !uri.isScheme('http') && !uri.isScheme('https') || uri.host.isEmpty) {
    return null;
  }
  return '${uri.scheme}://${uri.authority}';
}
