import 'package:dio/dio.dart';

import '../../models/account.dart';
import '../storage/credentials.dart';

/// Ajoute le jeton de l'espace (parent ou enfant) à chaque requête et gère le 401 :
///
/// - parent : le jeton d'accès (15 min) est renouvelé une seule fois avec le jeton de
///   renouvellement, puis la requête est rejouée ; si le renouvellement est refusé,
///   la session est fermée ;
/// - enfant : l'appareil a été délié par le parent, on revient au premier lancement.
///
/// `QueuedInterceptor` traite les erreurs une par une : si plusieurs requêtes reçoivent
/// un 401 en même temps, une seule renouvelle le jeton, les autres rejouent avec le nouveau.
class AuthInterceptor extends QueuedInterceptor {
  AuthInterceptor({
    required this.credentials,
    required this.bare,
    required this.onRefreshed,
    required this.onSignedOut,
  });

  /// Identifiants courants.
  final Credentials Function() credentials;

  /// Client sans intercepteur, pour renouveler le jeton et rejouer la requête.
  final Dio bare;
  final Future<void> Function(ParentTokens tokens) onRefreshed;
  final Future<void> Function() onSignedOut;

  static const _tokenKey = 'ludifun.token';

  /// `Options(extra: AuthInterceptor.anonymous)` : requête sans jeton (connexion, liaison…).
  static const anonymous = {'ludifun.anonymous': true};

  static bool _isAnonymous(RequestOptions options) => options.extra['ludifun.anonymous'] == true;

  static String? tokenOf(Credentials credentials) => switch (credentials) {
    ParentCredentials(:final accessToken) => accessToken,
    ChildCredentials(:final deviceToken) => deviceToken,
    NoCredentials() => null,
  };

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    final token = _isAnonymous(options) ? null : tokenOf(credentials());
    if (token != null) _authorize(options, token);
    handler.next(options);
  }

  @override
  Future<void> onError(DioException err, ErrorInterceptorHandler handler) async {
    final options = err.requestOptions;
    final used = options.extra[_tokenKey] as String?;
    if (err.response?.statusCode != 401 || used == null) return handler.next(err);

    final current = credentials();
    switch (current) {
      case ParentCredentials(:final accessToken) when accessToken != used:
        return _retry(options, accessToken, handler, err); // déjà renouvelé par une autre requête
      case ParentCredentials(:final refreshToken):
        final ParentTokens tokens;
        try {
          final response = await bare.post<Map<String, dynamic>>(
            '/v1/auth/refresh',
            data: {'refresh_token': refreshToken},
          );
          tokens = ParentTokens.fromJson(response.data!);
        } on DioException catch (refreshError) {
          if (refreshError.response?.statusCode == 401) await onSignedOut();
          return handler.next(err);
        }
        await onRefreshed(tokens);
        return _retry(options, tokens.accessToken, handler, err);
      case ChildCredentials(:final deviceToken) when deviceToken == used:
        await onSignedOut();
        return handler.next(err);
      case _:
        return handler.next(err);
    }
  }

  void _authorize(RequestOptions options, String token) {
    options.headers['Authorization'] = 'Bearer $token';
    options.extra[_tokenKey] = token;
  }

  Future<void> _retry(
    RequestOptions options,
    String token,
    ErrorInterceptorHandler handler,
    DioException original,
  ) async {
    _authorize(options, token);
    if (options.data is FormData) options.data = (options.data as FormData).clone();
    try {
      handler.resolve(await bare.fetch<dynamic>(options));
    } on DioException catch (error) {
      handler.next(error);
    }
  }
}
