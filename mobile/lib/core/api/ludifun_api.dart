import 'dart:typed_data';

import 'package:dio/dio.dart';

import '../../models/account.dart';
import '../../models/ai.dart';
import '../../models/figure.dart';
import '../../models/homework.dart';
import '../../models/lesson.dart';
import '../../models/parent.dart';
import '../../models/programme.dart';
import '../../models/rewards.dart';
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

  /// Avis sur l'application (tests en famille) : une note de 1 à 5 et/ou un message.
  /// L'enfant peut citer sa séance ; le parent, l'enfant concerné.
  Future<void> sendFeedback({
    int? rating,
    String? message,
    String? screen,
    String? sessionId,
    String? childId,
  }) => _call(
    () => _dio.post<void>(
      '/v1/feedback',
      data: {
        'rating': ?rating,
        'message': ?message,
        'screen': ?screen,
        'session_id': ?sessionId,
        'child_id': ?childId,
      },
    ),
  );

  // Espace parent ------------------------------------------------------------

  /// `firstName` : facultatif, pour « Bonjour Claire » dans les e-mails (arbitrage A2).
  Future<ParentTokens> register({
    required String email,
    required String password,
    String? firstName,
  }) => _call(() async {
    final r = await _dio.post<Json>(
      '/v1/auth/register',
      data: {
        'email': email,
        'password': password,
        'accepted_privacy_policy': true,
        'first_name': ?firstName,
      },
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
  Future<ParentProfile> parent() => _call(() async {
    final r = await _dio.get<Json>('/v1/parent');
    return ParentProfile.fromJson(r.data!);
  });

  /// Renvoie « Confirmez votre adresse » (3 fois par heure).
  Future<void> resendEmailVerification() => _call(() => _dio.post<void>('/v1/parent/verify-email'));

  /// Lien de l'e-mail ouvert dans l'application (sans être connecté).
  Future<void> verifyEmail(String token) => _call(
    () => _dio.post<void>('/v1/auth/verify-email', data: {'token': token}, options: _anonymous),
  );

  /// L'IA de la famille (espace parent) et les choix possibles.
  Future<AiSettings> aiSettings() => _call(() async {
    final r = await _dio.get<Json>('/v1/parent/ai');
    return AiSettings.fromJson(r.data!);
  });

  static Json _aiBody(
    String provider,
    String? model,
    String? baseUrl,
    String? apiKey, {
    bool? fallback,
  }) => {
    'provider': provider,
    'model': ?model,
    'base_url': ?baseUrl,
    'api_key': ?apiKey,
    'fallback': ?fallback,
  };

  /// `apiKey` null : garder la clé enregistrée (même fournisseur).
  Future<AiSettings> saveAiSettings(
    String provider, {
    String? model,
    String? baseUrl,
    String? apiKey,
    bool? fallback,
  }) => _call(() async {
    final r = await _dio.put<Json>(
      '/v1/parent/ai',
      data: _aiBody(provider, model, baseUrl, apiKey, fallback: fallback),
    );
    return AiSettings.fromJson(r.data!);
  });

  /// Permettre (ou non) la recherche de sources sur des sites éducatifs (étape 24).
  Future<AiSettings> setWebSources(bool enabled) => _call(() async {
    final r = await _dio.put<Json>('/v1/parent/ai/sources', data: {'enabled': enabled});
    return AiSettings.fromJson(r.data!);
  });

  /// Oublier une IA : sa clé est effacée (retour à l'IA du serveur si elle était active).
  Future<void> forgetAiProvider(String provider) =>
      _call(() => _dio.delete<void>('/v1/parent/ai/providers/$provider'));

  /// Revenir à l'IA du serveur (les clés enregistrées restent).
  Future<void> resetAiSettings() => _call(() => _dio.delete<void>('/v1/parent/ai'));

  /// « Tester » : le service répond-il, la clé est-elle acceptée ? (rien n'est facturé)
  Future<AiCheck> testAi(String provider, {String? model, String? baseUrl, String? apiKey}) =>
      _call(() async {
        final r = await _dio.post<Json>(
          '/v1/parent/ai/test',
          data: _aiBody(provider, model, baseUrl, apiKey),
        );
        return AiCheck.fromJson(r.data!);
      });

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

  /// Objectifs : `null` remet « libre » / « aucune ».
  Future<Child> setGoals(
    String id, {
    required int? dailyMinutes,
    required String? prioritySubject,
  }) => _call(() async {
    final r = await _dio.patch<Json>(
      '/v1/children/$id',
      data: {'daily_minutes': dailyMinutes, 'priority_subject': prioritySubject},
    );
    return Child.fromJson(r.data!);
  });

  Future<List<Exam>> exams(String childId) => _call(() async {
    final r = await _dio.get<List<dynamic>>('/v1/children/$childId/exams');
    return [for (final e in r.data!) Exam.fromJson(e as Json)];
  });

  Future<Exam> createExam(
    String childId, {
    required String title,
    required DateTime date,
    required List<String> lessonIds,
  }) => _call(() async {
    final day =
        '${date.year}-${date.month.toString().padLeft(2, '0')}-${date.day.toString().padLeft(2, '0')}';
    final r = await _dio.post<Json>(
      '/v1/children/$childId/exams',
      data: {'title': title, 'exam_date': day, 'lesson_ids': lessonIds},
    );
    return Exam.fromJson(r.data!);
  });

  Future<void> deleteExam(String childId, String examId) =>
      _call(() => _dio.delete<void>('/v1/children/$childId/exams/$examId'));

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

  /// Le programme de la classe de l'enfant, et où en sont les notions de ses leçons (§105).
  Future<Programme> programme(String childId) => _call(() async {
    final r = await _dio.get<Json>('/v1/children/$childId/programme');
    return Programme.fromJson(r.data!);
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

  Future<LessonContent> lessonContent(String childId, String lessonId) => _call(() async {
    final r = await _dio.get<Json>('/v1/children/$childId/lessons/$lessonId/content');
    return LessonContent.fromJson(r.data!);
  });

  /// Nouvelle version des questions d'une notion ; l'IA peut prendre une ou deux minutes.
  Future<NotionContent> reworkNotion(
    String childId,
    String lessonId,
    String knowledgeId, {
    required String reason,
    String? comment,
  }) => _call(() async {
    final r = await _dio.post<Json>(
      '/v1/children/$childId/lessons/$lessonId/notions/$knowledgeId/rework',
      data: {'reason': reason, 'comment': ?comment},
      options: Options(receiveTimeout: const Duration(minutes: 16)),
    );
    return NotionContent.fromJson(r.data!);
  });

  Future<LessonImages> lessonImages(String childId, String lessonId) => _call(() async {
    final r = await _dio.get<Json>('/v1/children/$childId/lessons/$lessonId/image');
    return LessonImages.fromJson(r.data!);
  });

  Future<LessonImage> approveImage(String childId, String lessonId) =>
      _imageDecision('/v1/children/$childId/lessons/$lessonId/image/approve');

  Future<LessonImage> rejectImage(String childId, String lessonId) =>
      _imageDecision('/v1/children/$childId/lessons/$lessonId/image/reject');

  /// Nouvelle image, préparée en arrière-plan ; la remarque du parent guide l'IA.
  Future<LessonImage> redoImage(String childId, String lessonId, {String? remark}) =>
      _imageDecision(
        '/v1/children/$childId/lessons/$lessonId/image/redo',
        data: {'remark': ?remark},
      );

  /// Image d'une notion (ou de la leçon) par son identifiant (étape 28).
  Future<LessonImage> decidePicture(
    String childId,
    String lessonId,
    String imageId, {
    required bool approve,
  }) => _imageDecision(
    '/v1/children/$childId/lessons/$lessonId/images/$imageId/${approve ? 'approve' : 'reject'}',
  );

  Future<LessonImage> redoPicture(
    String childId,
    String lessonId,
    String imageId, {
    String? remark,
  }) => _imageDecision(
    '/v1/children/$childId/lessons/$lessonId/images/$imageId/redo',
    data: {'remark': ?remark},
  );

  /// Ressources des sites de confiance d'une leçon, avec les essais de l'enfant (étape 30).
  Future<LessonResources> lessonResources(String childId, String lessonId) => _call(() async {
    final r = await _dio.get<Json>('/v1/children/$childId/lessons/$lessonId/resources');
    return LessonResources.fromJson(r.data!);
  });

  /// Masquée, l'enfant ne la voit plus ; affichée de nouveau, si.
  Future<void> setResourceHidden(
    String childId,
    String lessonId,
    String resourceId, {
    required bool hidden,
  }) => _call(() async {
    await _dio.post<Json>(
      '/v1/children/$childId/lessons/$lessonId/resources/$resourceId/${hidden ? 'hide' : 'show'}',
    );
  });

  /// Cherche (de nouveau) les ressources, en arrière-plan : relire la liste ensuite.
  Future<LessonResources> prepareResources(String childId, String lessonId) => _call(() async {
    final r = await _dio.post<Json>('/v1/children/$childId/lessons/$lessonId/resources/prepare');
    return LessonResources.fromJson(r.data!);
  });

  /// L'IA dit si des images aident, puis elles sont dessinées (leçon déjà analysée).
  Future<LessonImage> prepareImages(String childId, String lessonId) =>
      _imageDecision('/v1/children/$childId/lessons/$lessonId/images/prepare');

  Future<LessonImage> _imageDecision(String path, {Json? data}) => _call(() async {
    final r = await _dio.post<Json>(path, data: data);
    return LessonImage.fromJson(r.data!);
  });

  /// Fichier d'une image (parent ou enfant : le chemin vient du serveur).
  Future<Uint8List> imageBytes(String path) => _call(() async {
    final r = await _dio.get<List<int>>(path, options: Options(responseType: ResponseType.bytes));
    return Uint8List.fromList(r.data!);
  });

  Future<MistakesPage> mistakes(String childId, {int limit = 20, String? before}) =>
      _call(() async {
        final r = await _dio.get<Json>(
          '/v1/children/$childId/mistakes',
          queryParameters: {'limit': limit, 'before': ?before},
        );
        return MistakesPage.fromJson(r.data!);
      });

  /// Quand l'enfant a touché « Je n'ai pas compris », de la plus récente à la plus ancienne.
  Future<HelpRequestsPage> helpRequests(String childId, {int limit = 20, String? before}) =>
      _call(() async {
        final r = await _dio.get<Json>(
          '/v1/children/$childId/help-requests',
          queryParameters: {'limit': limit, 'before': ?before},
        );
        return HelpRequestsPage.fromJson(r.data!);
      });

  /// Questions signalées par l'enfant (🚩), de la plus récente à la plus ancienne.
  Future<QuestionReportsPage> questionReports(String childId, {int limit = 20, String? before}) =>
      _call(() async {
        final r = await _dio.get<Json>(
          '/v1/children/$childId/question-reports',
          queryParameters: {'limit': limit, 'before': ?before},
        );
        return QuestionReportsPage.fromJson(r.data!);
      });

  /// Le parent a regardé la question signalée.
  Future<void> markReportSeen(String childId, String reportId) =>
      _call(() => _dio.post<void>('/v1/children/$childId/question-reports/$reportId/seen'));

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

  /// XP, niveau, série et badges ; le parent précise l'enfant (`childId`).
  Future<Progress> progress({String? childId}) => _call(() async {
    final r = await _dio.get<Json>('/v1/me/progress', queryParameters: {'child_id': ?childId});
    return Progress.fromJson(r.data!);
  });

  Future<Mission> mission() => _call(() async {
    final r = await _dio.get<Json>('/v1/me/mission');
    return Mission.fromJson(r.data!);
  });

  Future<List<LessonSummary>> lessons({String? childId}) => _call(() async {
    final r = await _dio.get<List<dynamic>>('/v1/lessons', queryParameters: _forChild(childId));
    return [for (final lesson in r.data!) LessonSummary.fromJson(lesson as Json)];
  });

  /// `childId` : appel par un parent pour l'un de ses enfants.
  static Map<String, String>? _forChild(String? childId) =>
      childId == null ? null : {'child_id': childId};

  Future<Lesson> lesson(String id, {String? childId}) => _call(() async {
    final r = await _dio.get<Json>('/v1/lessons/$id', queryParameters: _forChild(childId));
    return Lesson.fromJson(r.data!);
  });

  /// Score d'un exercice noté, à la fin ; le serveur garde le meilleur pour le parent.
  Future<ResourceScore?> postResourceResult(
    String lessonId,
    String resourceId,
    ResourceScore score,
  ) => _call(() async {
    final r = await _dio.post<Json>(
      '/v1/lessons/$lessonId/resources/$resourceId/result',
      data: score.toJson(),
    );
    return switch (r.data?['best']) {
      final Json best => ResourceScore.fromJson(best),
      _ => null,
    };
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

  /// Mode devoirs : la photo de l'exercice (lue puis oubliée par le serveur).
  Future<Homework> homeworkFromPhoto(List<Uint8List> pages) => _call(() async {
    final form = FormData.fromMap({
      'pages': [
        for (final (i, page) in pages.indexed)
          MultipartFile.fromBytes(
            page,
            filename: 'exercice${i + 1}.jpg',
            contentType: DioMediaType('image', 'jpeg'),
          ),
      ],
    });
    final r = await _dio.post<Json>(
      '/v1/homework',
      data: form,
      options: Options(contentType: 'multipart/form-data', sendTimeout: const Duration(minutes: 2)),
    );
    return Homework.fromJson(r.data!);
  });

  /// Mode devoirs : l'énoncé recopié.
  Future<Homework> homeworkFromText(String text) => _call(() async {
    final r = await _dio.post<Json>('/v1/homework/text', data: {'text': text});
    return Homework.fromJson(r.data!);
  });

  Future<Homework> homework(String id) => _call(() async {
    final r = await _dio.get<Json>('/v1/homework/$id');
    return Homework.fromJson(r.data!);
  });

  /// Une étape de plus (indice, question, rappel, méthode).
  Future<Homework> homeworkNextStep(String id) => _call(() async {
    final r = await _dio.post<Json>('/v1/homework/$id/next-step');
    return Homework.fromJson(r.data!);
  });

  /// La réponse de l'enfant, vérifiée par le serveur.
  Future<Homework> homeworkAttempt(String id, String text) => _call(() async {
    final r = await _dio.post<Json>('/v1/homework/$id/attempts', data: {'text': text});
    return Homework.fromJson(r.data!);
  });

  /// La correction guidée (seulement après plusieurs essais).
  Future<Homework> homeworkSolution(String id) => _call(() async {
    final r = await _dio.post<Json>('/v1/homework/$id/solution');
    return Homework.fromJson(r.data!);
  });

  /// Parent : les exercices de l'enfant en mode devoirs.
  Future<HomeworkPage> childHomework(String childId, {int limit = 20, String? before}) =>
      _call(() async {
        final r = await _dio.get<Json>(
          '/v1/children/$childId/homework',
          queryParameters: {'limit': limit, 'before': ?before},
        );
        return HomeworkPage.fromJson(r.data!);
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

  /// La séance telle que le serveur l'envoie, pour la garder sur le téléphone (hors connexion).
  Future<Json> sessionData(String id) => _call(() async {
    final r = await _dio.get<Json>('/v1/sessions/$id');
    return r.data!;
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
    DateTime? answeredAt,
  }) => _call(() async {
    final r = await _dio.post<Json>(
      '/v1/sessions/$sessionId/attempts',
      data: {
        'item_id': itemId,
        'response': response,
        'duration_ms': ?durationMs,
        // Séance jouée hors connexion : l'heure de la réponse sur le téléphone.
        'answered_at': ?answeredAt?.toUtc().toIso8601String(),
      },
    );
    return Correction.fromJson(r.data!);
  });

  /// « Je n'ai pas compris » : l'aide suivante pour cette activité (le serveur retient le niveau).
  Future<HelpStep> help(String sessionId, String itemId) => _call(() async {
    final r = await _dio.post<Json>('/v1/sessions/$sessionId/items/$itemId/help');
    return HelpStep.fromJson(r.data!);
  });

  /// 🚩 L'enfant signale la question ; le parent la verra. Ne change ni la note ni la progression.
  Future<void> reportQuestion(String sessionId, String itemId, ReportReason reason) => _call(
    () => _dio.post<void>(
      '/v1/sessions/$sessionId/items/$itemId/report',
      data: {'reason': reason.code},
    ),
  );

  /// Reprise des erreurs, après la dernière activité principale (liste vide s'il n'y en a pas).
  /// `bonusOffer` : proposer « encore 3 défis ? » (séance réussie et rapide, sans reprise).
  Future<({List<SessionItem> items, bool bonusOffer})> replay(String sessionId) => _call(() async {
    final r = await _dio.post<Json>('/v1/sessions/$sessionId/replay');
    return (
      items: [
        for (final item in r.data!['items'] as List<dynamic>) SessionItem.fromJson(item as Json),
      ],
      bonusOffer: r.data!['bonus_offer'] as bool? ?? false,
    );
  });

  /// Défis bonus (une fois par séance).
  Future<List<SessionItem>> extend(String sessionId) => _call(() async {
    final r = await _dio.post<Json>('/v1/sessions/$sessionId/extend');
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

  /// Carte ou schéma des activités « carte » et « coloriage » (étape 22) : données publiques.
  Future<Figure> figure(String id) => _call(() async {
    final r = await _dio.get<Json>('/v1/figures/$id', options: _anonymous);
    return Figure.fromJson(r.data!);
  });

  /// Détail d'une séance pour le parent : chaque activité, son résultat et sa raison (§126).
  Future<SessionDetail> sessionDetail(String childId, String sessionId) => _call(() async {
    final r = await _dio.get<Json>('/v1/children/$childId/sessions/$sessionId');
    return SessionDetail.fromJson(r.data!);
  });
}
