import 'package:dio/dio.dart';

import '../../models/account.dart';
import 'api_exception.dart';
import 'auth_interceptor.dart';

Dio buildDio(String baseUrl) => Dio(
  BaseOptions(
    baseUrl: baseUrl,
    connectTimeout: const Duration(seconds: 10),
    receiveTimeout: const Duration(seconds: 30),
    contentType: Headers.jsonContentType,
    responseType: ResponseType.json,
  ),
);

/// Routes de l'API v1 (§11). Toute erreur devient une [ApiException].
class LudifunApi {
  LudifunApi(this._dio);

  final Dio _dio;
  static final _anonymous = Options(extra: AuthInterceptor.anonymous);

  Future<T> _call<T>(Future<T> Function() request) async {
    try {
      return await request();
    } on DioException catch (error) {
      throw ApiException.fromDio(error);
    }
  }

  // Espace parent ------------------------------------------------------------

  Future<ParentTokens> register({required String email, required String password}) =>
      _call(() async {
        final r = await _dio.post<Json>(
          '/v1/auth/register',
          data: {'email': email, 'password': password, 'accepted_privacy_policy': true},
          options: _anonymous,
        );
        return ParentTokens.fromJson(r.data!);
      });

  Future<ParentTokens> login({required String email, required String password}) => _call(() async {
    final r = await _dio.post<Json>(
      '/v1/auth/login',
      data: {'email': email, 'password': password},
      options: _anonymous,
    );
    return ParentTokens.fromJson(r.data!);
  });

  Future<void> logout(String refreshToken) => _call(
    () => _dio.post<void>(
      '/v1/auth/logout',
      data: {'refresh_token': refreshToken},
      options: _anonymous,
    ),
  );

  Future<List<Child>> children() => _call(() async {
    final r = await _dio.get<List<dynamic>>('/v1/children');
    return [for (final child in r.data!) Child.fromJson(child as Json)];
  });

  // Espace enfant ------------------------------------------------------------

  Future<LinkResult> link({required String code, String? deviceName}) => _call(() async {
    final r = await _dio.post<Json>(
      '/v1/link',
      data: {'code': code, 'device_name': ?deviceName},
      options: _anonymous,
    );
    return LinkResult.fromJson(r.data!);
  });

  Future<Child> me() => _call(() async {
    final r = await _dio.get<Json>('/v1/me');
    return Child.fromJson(r.data!);
  });
}
