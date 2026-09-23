import 'dart:typed_data';

import 'package:dio/dio.dart';

import '../../models/account.dart';
import '../../models/lesson.dart';
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

  /// Liaison par le code à 6 chiffres ou par le contenu du QR code.
  Future<LinkResult> link({String? code, String? qrToken, String? deviceName}) => _call(() async {
    final r = await _dio.post<Json>(
      '/v1/link',
      data: {'code': ?code, 'qr_token': ?qrToken, 'device_name': ?deviceName},
      options: _anonymous,
    );
    return LinkResult.fromJson(r.data!);
  });

  /// « Ce n'est pas moi » : l'appareil rend le jeton qu'il vient de recevoir.
  Future<void> unlinkDevice(String deviceToken) => _call(
    () => _dio.delete<void>(
      '/v1/me/device',
      options: Options(
        headers: {'Authorization': 'Bearer $deviceToken'},
        extra: AuthInterceptor.anonymous,
      ),
    ),
  );

  Future<Child> me() => _call(() async {
    final r = await _dio.get<Json>('/v1/me');
    return Child.fromJson(r.data!);
  });

  Future<Mission> mission() => _call(() async {
    final r = await _dio.get<Json>('/v1/me/mission');
    return Mission.fromJson(r.data!);
  });

  Future<List<LessonSummary>> lessons() => _call(() async {
    final r = await _dio.get<List<dynamic>>('/v1/lessons');
    return [for (final lesson in r.data!) LessonSummary.fromJson(lesson as Json)];
  });

  Future<Lesson> lesson(String id) => _call(() async {
    final r = await _dio.get<Json>('/v1/lessons/$id');
    return Lesson.fromJson(r.data!);
  });

  /// Écran 2 : pages déjà compressées (JPEG), dans l'ordre.
  Future<Lesson> uploadLesson(
    List<Uint8List> pages, {
    void Function(int sent, int total)? onProgress,
  }) => _call(() async {
    final form = FormData.fromMap({
      'pages': [
        for (final (i, page) in pages.indexed)
          MultipartFile.fromBytes(
            page,
            filename: 'page${i + 1}.jpg',
            contentType: DioMediaType('image', 'jpeg'),
          ),
      ],
    });
    final r = await _dio.post<Json>(
      '/v1/lessons',
      data: form,
      options: Options(contentType: 'multipart/form-data', sendTimeout: const Duration(minutes: 2)),
      onSendProgress: onProgress,
    );
    return lesson(r.data!['id'] as String);
  });

  Future<void> retryLesson(String id) => _call(() => _dio.post<Json>('/v1/lessons/$id/retry'));

  Future<void> deleteLesson(String id) => _call(() => _dio.delete<void>('/v1/lessons/$id'));

  Future<Lesson> setGrade(String id, String grade) => _call(() async {
    final r = await _dio.patch<Json>('/v1/lessons/$id', data: {'grade': grade});
    return Lesson.fromJson(r.data!);
  });

  /// Séance adaptée à la maîtrise, ou reprise de la séance en cours.
  /// Lève [ApiException] `nothing_to_review` si tout est à jour.
  Future<RevisionSession> startSession(String lessonId) => _call(() async {
    final r = await _dio.post<Json>('/v1/lessons/$lessonId/sessions', data: <String, Object>{});
    return RevisionSession.fromJson(r.data!);
  });
}
