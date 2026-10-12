import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../models/account.dart' show Json;
import '../models/session.dart';
import 'api/api_exception.dart';
import 'session.dart';

/// Activités qui chargent un dessin ou une image depuis le serveur : sautées hors connexion
/// (la séance se termine sans elles, le serveur l'accepte).
const onlineOnlyTypes = {'MAP', 'COLORING', 'PICTURE_MATCH', 'PICTURE_FIND'};

bool playableOffline(SessionItem item) =>
    !onlineOnlyTypes.contains(item.type) && item.payload['image'] == null;

bool isOfflineError(ApiException error) => error.code == 'network' || error.code == 'timeout';

/// Une réponse donnée hors connexion, envoyée au retour du réseau (le serveur la corrige).
class PendingAnswer {
  const PendingAnswer({
    required this.itemId,
    required this.response,
    required this.answeredAt,
    this.durationMs,
  });

  factory PendingAnswer.fromJson(Json json) => PendingAnswer(
    itemId: json['item_id'] as String,
    response: (json['response'] as Map).cast<String, Object?>(),
    answeredAt: DateTime.parse(json['answered_at'] as String),
    durationMs: json['duration_ms'] as int?,
  );

  final String itemId;
  final Map<String, Object?> response;
  final DateTime answeredAt;
  final int? durationMs;

  Json toJson() => {
    'item_id': itemId,
    'response': response,
    'answered_at': answeredAt.toUtc().toIso8601String(),
    'duration_ms': durationMs,
  };
}

/// Une séance téléchargée : ses activités (sans les solutions, comme toujours), et les réponses
/// pas encore envoyées.
class OfflinePack {
  const OfflinePack({
    required this.sessionJson,
    required this.downloadedAt,
    this.lessonTitle,
    this.answers = const [],
    this.finished = false,
  });

  factory OfflinePack.fromJson(Json json) => OfflinePack(
    sessionJson: (json['session'] as Map).cast<String, dynamic>(),
    lessonTitle: json['lesson_title'] as String?,
    downloadedAt: DateTime.parse(json['downloaded_at'] as String),
    answers: [
      for (final a in json['answers'] as List<dynamic>? ?? const [])
        PendingAnswer.fromJson((a as Map).cast<String, dynamic>()),
    ],
    finished: json['finished'] as bool? ?? false,
  );

  final Json sessionJson;
  final String? lessonTitle;
  final DateTime downloadedAt;
  final List<PendingAnswer> answers;

  /// Jouée jusqu'au bout hors connexion : le bilan sera demandé après l'envoi des réponses.
  final bool finished;

  RevisionSession get session => RevisionSession.fromJson(sessionJson);
  String get sessionId => sessionJson['id'] as String;
  String get lessonId => sessionJson['lesson_id'] as String;
  bool get waiting => answers.isNotEmpty || finished;

  OfflinePack copyWith({List<PendingAnswer>? answers, bool? finished}) => OfflinePack(
    sessionJson: sessionJson,
    lessonTitle: lessonTitle,
    downloadedAt: downloadedAt,
    answers: answers ?? this.answers,
    finished: finished ?? this.finished,
  );

  Json toJson() => {
    'session': sessionJson,
    'lesson_title': lessonTitle,
    'downloaded_at': downloadedAt.toUtc().toIso8601String(),
    'answers': [for (final a in answers) a.toJson()],
    'finished': finished,
  };
}

abstract interface class OfflineStore {
  Future<List<OfflinePack>> read();

  Future<void> write(List<OfflinePack> packs);
}

class SecureOfflineStore implements OfflineStore {
  SecureOfflineStore([FlutterSecureStorage? storage])
    : _storage = storage ?? const FlutterSecureStorage();

  static const key = 'ludifun.offline';
  final FlutterSecureStorage _storage;

  @override
  Future<List<OfflinePack>> read() async {
    try {
      final raw = await _storage.read(key: key);
      if (raw == null) return const [];
      return [
        for (final p in jsonDecode(raw) as List<dynamic>)
          OfflinePack.fromJson((p as Map).cast<String, dynamic>()),
      ];
    } on Object {
      return const []; // contenu illisible : rien de téléchargé
    }
  }

  @override
  Future<void> write(List<OfflinePack> packs) =>
      _storage.write(key: key, value: jsonEncode([for (final p in packs) p.toJson()]));
}

class MemoryOfflineStore implements OfflineStore {
  List<OfflinePack> packs = [];

  @override
  Future<List<OfflinePack>> read() async => packs;

  @override
  Future<void> write(List<OfflinePack> packs) async => this.packs = [...packs];
}

final offlineStoreProvider = Provider<OfflineStore>((ref) => SecureOfflineStore());

/// Séances téléchargées, pour l'accueil (à jouer, à envoyer).
final offlinePacksProvider = FutureProvider.autoDispose<List<OfflinePack>>(
  (ref) => ref.watch(offlineStoreProvider).read(),
);

/// Une séance jouée hors connexion, corrigée au retour du réseau.
typedef SyncedSession = ({String? lessonTitle, double scoreOn10});

final offlineSessionsProvider = Provider<OfflineSessions>(OfflineSessions.new);

class OfflineSessions {
  OfflineSessions(this.ref);

  final Ref ref;

  /// Au plus 3 séances gardées : les plus anciennes déjà envoyées partent d'abord.
  static const maxPacks = 3;

  OfflineStore get _store => ref.read(offlineStoreProvider);

  Future<OfflinePack?> pack(String sessionId) async =>
      (await _store.read()).where((p) => p.sessionId == sessionId).firstOrNull;

  Future<OfflinePack?> forLesson(String lessonId) async =>
      (await _store.read()).where((p) => p.lessonId == lessonId).firstOrNull;

  Future<void> _update(String sessionId, OfflinePack? Function(OfflinePack) change) async {
    final stored = await _store.read();
    if (!stored.any((p) => p.sessionId == sessionId)) return; // rien de téléchargé : rien à écrire
    final packs = <OfflinePack>[];
    for (final p in stored) {
      final updated = p.sessionId == sessionId ? change(p) : p;
      if (updated != null) packs.add(updated);
    }
    await _store.write(packs);
    ref.invalidate(offlinePacksProvider);
  }

  /// Garde la séance sur le téléphone, pour la jouer sans Internet.
  Future<void> download(String sessionId, {String? lessonTitle}) async {
    final json = await ref.read(apiProvider).sessionData(sessionId);
    final packs = [...await _store.read()]..removeWhere((p) => p.sessionId == sessionId);
    while (packs.length >= maxPacks) {
      final old = packs.where((p) => !p.waiting).firstOrNull;
      if (old == null) break;
      packs.remove(old);
    }
    packs.add(
      OfflinePack(
        sessionJson: json,
        lessonTitle: lessonTitle,
        downloadedAt: ref.read(nowForOfflineProvider)(),
      ),
    );
    await _store.write(packs);
    ref.invalidate(offlinePacksProvider);
  }

  Future<void> record(String sessionId, PendingAnswer answer) =>
      _update(sessionId, (p) => p.copyWith(answers: [...p.answers, answer]));

  Future<void> finish(String sessionId) => _update(sessionId, (p) => p.copyWith(finished: true));

  Future<void> forget(String sessionId) => _update(sessionId, (_) => null);

  /// Envoie les réponses d'une séance, dans l'ordre ; `false` si le réseau manque encore.
  Future<bool> sendAnswers(String sessionId) async {
    final pack = await this.pack(sessionId);
    if (pack == null) return true;
    final api = ref.read(apiProvider);
    for (final answer in pack.answers) {
      try {
        await api.answer(
          sessionId,
          answer.itemId,
          answer.response,
          durationMs: answer.durationMs,
          answeredAt: answer.answeredAt,
        );
      } on ApiException catch (error) {
        if (isOfflineError(error)) return false;
        if (error.code == 'session_closed' || error.code == 'session_not_found') {
          await forget(sessionId); // séance terminée ou abandonnée ailleurs
          return true;
        }
        // déjà répondue, ou réponse refusée : on passe à la suivante
      }
      await _update(sessionId, (p) => p.copyWith(answers: p.answers.skip(1).toList()));
    }
    return true;
  }

  /// Au retour du réseau : envoie tout ce qui attend, et demande le bilan des séances finies.
  Future<List<SyncedSession>> sync() async {
    final synced = <SyncedSession>[];
    for (final pack in await _store.read()) {
      if (!pack.waiting) continue;
      if (!await sendAnswers(pack.sessionId)) return synced;
      if (!pack.finished || await this.pack(pack.sessionId) == null) continue;
      try {
        final report = await ref.read(apiProvider).complete(pack.sessionId);
        synced.add((lessonTitle: pack.lessonTitle, scoreOn10: report.scoreOn10));
      } on ApiException catch (error) {
        if (isOfflineError(error)) return synced;
      }
      await forget(pack.sessionId);
    }
    return synced;
  }
}

/// Horloge des réponses hors connexion, remplaçable dans les tests.
final nowForOfflineProvider = Provider<DateTime Function()>((ref) => DateTime.now);
