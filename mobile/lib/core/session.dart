import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/account.dart';
import 'api/auth_interceptor.dart';
import 'api/ludifun_api.dart';
import 'config.dart';
import 'storage/credentials.dart';

final credentialStoreProvider = Provider<CredentialStore>((ref) => SecureCredentialStore());

/// Adresse enregistrée sur ce téléphone (versions de test), lue au démarrage par `main`.
final savedApiUrlProvider = Provider<String?>((ref) => null);

final apiBaseUrlProvider = NotifierProvider<ApiUrlController, String>(ApiUrlController.new);

class ApiUrlController extends Notifier<String> {
  @override
  String build() => ref.read(savedApiUrlProvider) ?? apiBaseUrl();

  Future<void> set(String url) async {
    await saveApiUrl(url);
    state = url;
  }
}

/// Client HTTP brut (sans jeton) : surchargé dans les tests par un faux serveur.
final bareDioProvider = Provider<Dio>((ref) => buildDio(ref.watch(apiBaseUrlProvider)));

final dioProvider = Provider<Dio>((ref) {
  final bare = ref.watch(bareDioProvider);
  final dio = Dio(bare.options)..httpClientAdapter = bare.httpClientAdapter;
  final session = ref.read(sessionProvider.notifier);
  dio.interceptors.add(
    AuthInterceptor(
      credentials: session.current,
      bare: bare,
      onRefreshed: session.refreshed,
      onSignedOut: session.forget,
    ),
  );
  return dio;
});

final apiProvider = Provider<LudifunApi>((ref) => LudifunApi(ref.watch(dioProvider)));

final sessionProvider = AsyncNotifierProvider<SessionController, Credentials>(
  SessionController.new,
);

/// Identifiants de l'appareil, lus au démarrage dans le stockage sécurisé.
class SessionController extends AsyncNotifier<Credentials> {
  @override
  Future<Credentials> build() => ref.read(credentialStoreProvider).read();

  Credentials current() => state.value ?? const NoCredentials();

  Future<void> _save(Credentials credentials) async {
    await ref.read(credentialStoreProvider).write(credentials);
    state = AsyncData(credentials);
  }

  Future<void> signedIn(ParentTokens tokens) => _save(
    ParentCredentials(
      accessToken: tokens.accessToken,
      refreshToken: tokens.refreshToken,
      email: tokens.email,
    ),
  );

  Future<void> refreshed(ParentTokens tokens) => signedIn(tokens);

  Future<void> linked(LinkResult result) => _save(
    ChildCredentials(
      deviceToken: result.deviceToken,
      childId: result.child.id,
      displayName: result.child.displayName,
    ),
  );

  /// Oubli local des identifiants (session expirée, appareil délié).
  Future<void> forget() => _save(const NoCredentials());

  /// Déconnexion du parent : le jeton de renouvellement est révoqué côté serveur.
  Future<void> signOut() async {
    if (current() case ParentCredentials(:final refreshToken)) {
      try {
        await ref.read(apiProvider).logout(refreshToken);
      } on Exception {
        // hors ligne : le jeton expirera de lui-même (30 jours)
      }
    }
    await forget();
  }
}
