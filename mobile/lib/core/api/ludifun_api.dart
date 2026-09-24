import 'dart:typed_data';

import 'package:dio/dio.dart';

import '../../models/account.dart';
import '../../models/lesson.dart';
import '../../models/parent.dart';
import '../../models/session.dart';
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

  Future<void> requestPasswordReset(String email) => _call(
    () => _dio.post<Json>('/v1/auth/password-reset', data: {'email': email}, options: _anonymous),
  );

  Future<void> confirmPasswordReset({required String token, required String newPassword}) => _call(
    () => _dio.post<void>(
      '/v1/auth/password-reset/confirm',
      data: {'token': token, 'new_password': newPassword},
      options: _anonymous,
    ),
  );

  /// Droit à l'effacement : le compte, la famille et tous les enfants.
  Future<void> deleteAccount() => _call(() => _dio.delete<void>('/v1/parent'));

  Future<Child> createChild({required String displayName, required String grade, String? avatar}) =>
      _call(() async {
        final r = await _dio.post<Json>(
          '/v1/children',
          data: {
            'display_name': displayName,
            'grade': grade,
            'avatar': ?avatar,
            'parental_consent': true,
          },
        );
        return Child.fromJson(r.data!);
      });

  Future<Child> updateChild(String id, {String? displayName, String? grade, String? avatar}) =>
      _call(() async {
        final r = await _dio.patch<Json>(
          '/v1/children/$id',
          data: {'display_name': ?displayName, 'grade': ?grade, 'avatar': ?avatar},
        );
        return Child.fromJson(r.data!);
      });

  Future<void> deleteChild(String id) => _call(() => _dio.delete<void>('/v1/children/$id'));

  Future<LinkCode> linkCode(String childId) => _call(() async {
    final r = await _dio.post<Json>('/v1/children/$childId/link-codes');
    return LinkCode.fromJson(r.data!);
  });

  Future<List<Device>> devices(String childId) => _call(() async {
    final r = await _dio.get<List<dynamic>>('/v1/children/$childId/devices');
    return [for (final d in r.data!) Device.fromJson(d as Json)];
  });

  /// §16.2 : toutes les données de l'enfant, en JSON (nom de fichier proposé par le serveur).
  Future<({String filename, Uint8List bytes})> exportChild(String childId) => _call(() async {
    final r = await _dio.get<List<int>>(
      '/v1/children/$childId/export',
      options: Options(responseType: ResponseType.bytes),
    );
    final disposition = r.headers.value('content-disposition') ?? '';
    final filename =
        RegExp(r'filename="([^"]+)"').firstMatch(disposition)?.group(1) ?? 'ludifun-$childId.json';
    return (filename: filename, bytes: Uint8List.fromList(r.data!));
  });

  Future<void> revokeDevice(String childId, String deviceId) =>
      _call(() => _dio.delete<void>('/v1/children/$childId/devices/$deviceId'));

  Future<Dashboard> dashboard(String childId, {int weeks = 4}) => _call(() async {
    final r = await _dio.get<Json>(
      '/v1/children/$childId/dashboard',
      queryParameters: {'weeks': weeks},
    );
    return Dashboard.fromJson(r.data!);
  });

  Future<List<LessonProgress>> childSkills(String childId) => _call(() async {
    final r = await _dio.get<Json>('/v1/children/$childId/skills');
    return [
      for (final lesson in r.data!['lessons'] as List<dynamic>)
        LessonProgress.fromJson(lesson as Json),
    ];
  });

  Future<HistoryPage> history(String childId, {int limit = 20, String? before}) => _call(() async {
    final r = await _dio.get<Json>(
      '/v1/children/$childId/history',
      queryParameters: {'limit': limit, 'before': ?before},
    );
    return HistoryPage.fromJson(r.data!);
  });

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

  /// `childId` : appel par un parent pour l'un de ses enfants.
  static Map<String, String>? _forChild(String? childId) =>
      childId == null ? null : {'child_id': childId};

  Future<Lesson> lesson(String id, {String? childId}) => _call(() async {
    final r = await _dio.get<Json>('/v1/lessons/$id', queryParameters: _forChild(childId));
    return Lesson.fromJson(r.data!);
  });

  /// Écran 2 : pages déjà compressées (JPEG), dans l'ordre.
  Future<Lesson> uploadLesson(
    List<Uint8List> pages, {
    void Function(int sent, int total)? onProgress,
    String? childId,
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
      queryParameters: _forChild(childId),
      options: Options(contentType: 'multipart/form-data', sendTimeout: const Duration(minutes: 2)),
      onSendProgress: onProgress,
    );
    return lesson(r.data!['id'] as String, childId: childId);
  });

  /// Leçon collée ou tapée : même analyse que pour une photo.
  Future<Lesson> lessonFromText(String text, {String? childId}) => _call(() async {
    final r = await _dio.post<Json>(
      '/v1/lessons/text',
      data: {'text': text},
      queryParameters: _forChild(childId),
    );
    return lesson(r.data!['id'] as String, childId: childId);
  });

  /// « Peux-tu vérifier ? » : `status` confirmed, corrected (avec `text`) ou unknown, par passage.
  Future<void> reviewLesson(
    String id,
    List<({String itemId, String status, String? text})> answers, {
    String? childId,
  }) => _call(
    () => _dio.post<Json>(
      '/v1/lessons/$id/review',
      data: {
        'answers': [
          for (final a in answers) {'item_id': a.itemId, 'status': a.status, 'text': ?a.text},
        ],
      },
      queryParameters: _forChild(childId),
    ),
  );

  Future<void> retryLesson(String id, {String? childId}) =>
      _call(() => _dio.post<Json>('/v1/lessons/$id/retry', queryParameters: _forChild(childId)));

  Future<void> deleteLesson(String id, {String? childId}) =>
      _call(() => _dio.delete<void>('/v1/lessons/$id', queryParameters: _forChild(childId)));

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

  Future<RevisionSession> session(String id) => _call(() async {
    final r = await _dio.get<Json>('/v1/sessions/$id');
    return RevisionSession.fromJson(r.data!);
  });

  /// Écran 6. `{"skipped": true}` : activité inconnue de cette version, non notée.
  Future<Correction> answer(
    String sessionId,
    String itemId,
    Map<String, Object?> response, {
    int? durationMs,
  }) => _call(() async {
    final r = await _dio.post<Json>(
      '/v1/sessions/$sessionId/attempts',
      data: {'item_id': itemId, 'response': response, 'duration_ms': ?durationMs},
    );
    return Correction.fromJson(r.data!);
  });

  /// « Je n'ai pas compris » : l'aide suivante pour cette activité (le serveur retient le niveau).
  Future<HelpStep> help(String sessionId, String itemId) => _call(() async {
    final r = await _dio.post<Json>('/v1/sessions/$sessionId/items/$itemId/help');
    return HelpStep.fromJson(r.data!);
  });

  /// Reprise des erreurs, après la dernière activité principale (liste vide s'il n'y en a pas).
  Future<List<SessionItem>> replay(String sessionId) => _call(() async {
    final r = await _dio.post<Json>('/v1/sessions/$sessionId/replay');
    return [
      for (final item in r.data!['items'] as List<dynamic>) SessionItem.fromJson(item as Json),
    ];
  });

  Future<Report> complete(String sessionId) => _call(() async {
    final r = await _dio.post<Json>('/v1/sessions/$sessionId/complete');
    return Report.fromJson(r.data!);
  });

  /// « Revoir mes erreurs » : nouvelle séance courte sur les notions ratées.
  Future<RevisionSession> errorsSession(String sessionId) => _call(() async {
    final r = await _dio.post<Json>('/v1/sessions/$sessionId/errors-session');
    return RevisionSession.fromJson(r.data!);
  });
}
