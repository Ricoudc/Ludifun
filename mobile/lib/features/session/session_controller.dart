import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_exception.dart';
import '../../core/session.dart';
import '../../models/session.dart';
import '../home/home_providers.dart';
import 'activities/activity_registry.dart';

/// §14.4 : loading → question ⇄ submitting → correction → question (suivante)
///   └→ fin des activités principales : reprise des erreurs → question …
///   └→ fin : completing → report
enum Phase {
  loading,
  question,
  submitting,
  correction,

  /// « Encore 3 défis ? » après une séance réussie et rapide.
  bonusOffer,
  completing,
  report,
  finished,
  error,
}

class SessionState {
  const SessionState({
    this.phase = Phase.loading,
    this.items = const [],
    this.current,
    this.correction,
    this.report,
    this.error,
  });

  final Phase phase;

  /// Activités principales puis reprise des erreurs, dans l'ordre.
  final List<SessionItem> items;
  final SessionItem? current;
  final Correction? correction;
  final Report? report;
  final String? error;

  bool get inReplay => current?.block == Block.replay;

  bool get inBonus => current?.block == Block.bonus;

  /// Reprise des erreurs et défis bonus sont comptés à part.
  static int _groupOf(Block block) => switch (block) {
    Block.replay => 1,
    Block.bonus => 2,
    _ => 0,
  };

  List<SessionItem> get _group => [
    for (final item in items)
      if (_groupOf(item.block) == _groupOf(current?.block ?? Block.core)) item,
  ];

  /// « Question 3 / 8 » ou « Reprise des erreurs 1 / 2 ».
  (int, int) get counter {
    final group = _group;
    return (group.indexWhere((i) => i.id == current?.id) + 1, group.length);
  }

  /// Avancement des activités principales (0 à 1).
  double get progress {
    final main = [
      for (final item in items)
        if (_groupOf(item.block) == 0) item,
    ];
    if (main.isEmpty) return 0;
    return main.where((i) => i.answered).length / main.length;
  }

  SessionState copyWith({
    Phase? phase,
    List<SessionItem>? items,
    SessionItem? current,
    Correction? correction,
    Report? report,
    String? error,
  }) => SessionState(
    phase: phase ?? this.phase,
    items: items ?? this.items,
    current: current ?? this.current,
    correction: correction,
    report: report ?? this.report,
    error: error,
  );
}

/// Horloge de la durée des réponses, remplaçable dans les tests.
final stopwatchProvider = Provider<DateTime Function()>((ref) => DateTime.now);

final sessionControllerProvider = NotifierProvider.autoDispose
    .family<SessionController, SessionState, String>(SessionController.new);

class SessionController extends Notifier<SessionState> {
  SessionController(this.sessionId);

  final String sessionId;
  bool _replayRequested = false;
  DateTime? _shownAt;

  @override
  SessionState build() {
    Future.microtask(load);
    return const SessionState();
  }

  Future<void> load() async {
    state = state.copyWith(phase: Phase.loading);
    try {
      final session = await ref.read(apiProvider).session(sessionId);
      if (session.status != 'active') {
        state = state.copyWith(phase: Phase.finished, items: session.items);
        return;
      }
      final items = [...session.items]..sort((a, b) => a.position.compareTo(b.position));
      _replayRequested = items.any((i) => i.block == Block.replay);
      state = state.copyWith(items: items);
      await _advance();
    } on ApiException catch (error) {
      _fail(error);
    }
  }

  /// Réponse de l'enfant à l'activité affichée.
  Future<void> submit(Map<String, Object?> response) async {
    final item = state.current;
    if (item == null || state.phase != Phase.question) return;
    state = state.copyWith(phase: Phase.submitting);
    final shownAt = _shownAt;
    final durationMs = shownAt == null
        ? null
        : ref.read(stopwatchProvider)().difference(shownAt).inMilliseconds.clamp(0, 3600000);
    try {
      final correction = await ref
          .read(apiProvider)
          .answer(sessionId, item.id, response, durationMs: durationMs);
      // Remédiation : les activités insérées se jouent juste après celle-ci.
      final marked = _mark(item, correction.result);
      final at = marked.indexWhere((i) => i.id == item.id) + 1;
      final known = {for (final i in marked) i.id};
      state = state.copyWith(
        phase: Phase.correction,
        items: [
          ...marked.take(at),
          ...correction.insertedItems.where((i) => !known.contains(i.id)),
          ...marked.skip(at),
        ],
        correction: correction,
      );
    } on ApiException catch (error) {
      if (error.code == 'already_answered') return load(); // double envoi : on se recale
      _fail(error);
    }
  }

  /// « Continuer » après la correction.
  Future<void> next() async {
    if (state.phase != Phase.correction) return;
    await _advance();
  }

  Future<void> _advance() async {
    try {
      while (true) {
        final next = state.items.where((i) => !i.answered).firstOrNull;
        if (next == null) {
          if (_replayRequested) {
            await _complete();
            return;
          }
          state = state.copyWith(phase: Phase.loading);
          final replay = await ref.read(apiProvider).replay(sessionId);
          _replayRequested = true;
          final known = {for (final i in state.items) i.id};
          state = state.copyWith(
            items: [...state.items, ...replay.items.where((i) => !known.contains(i.id))],
          );
          if (replay.items.isEmpty && replay.bonusOffer) {
            state = state.copyWith(phase: Phase.bonusOffer);
            return;
          }
          continue;
        }
        if (!activityRegistry.containsKey(next.type)) {
          // Type inconnu (serveur plus récent) : sauté proprement, non noté (§14.3).
          await ref.read(apiProvider).answer(sessionId, next.id, {'skipped': true});
          state = state.copyWith(items: _mark(next, AttemptResult.skipped));
          continue;
        }
        _shownAt = ref.read(stopwatchProvider)();
        state = state.copyWith(phase: Phase.question, current: next);
        return;
      }
    } on ApiException catch (error) {
      _fail(error);
    }
  }

  Future<void> _complete() async {
    state = state.copyWith(phase: Phase.completing);
    try {
      final report = await ref.read(apiProvider).complete(sessionId);
      state = state.copyWith(phase: Phase.report, report: report);
      ref
        ..invalidate(lessonsProvider)
        ..invalidate(missionProvider);
    } on ApiException catch (error) {
      if (error.code == 'session_closed') {
        state = state.copyWith(phase: Phase.finished);
        return;
      }
      _fail(error);
    }
  }

  /// « Encore 3 défis ? » : oui.
  Future<void> acceptBonus() async {
    if (state.phase != Phase.bonusOffer) return;
    state = state.copyWith(phase: Phase.loading);
    try {
      final bonus = await ref.read(apiProvider).extend(sessionId);
      final known = {for (final i in state.items) i.id};
      state = state.copyWith(items: [...state.items, ...bonus.where((i) => !known.contains(i.id))]);
      await _advance();
    } on ApiException catch (error) {
      _fail(error);
    }
  }

  /// « Encore 3 défis ? » : non, on passe au bilan.
  Future<void> declineBonus() async {
    if (state.phase == Phase.bonusOffer) await _complete();
  }

  /// « Revoir mes erreurs » : identifiant de la nouvelle séance.
  Future<String?> reviewErrors() async {
    try {
      return (await ref.read(apiProvider).errorsSession(sessionId)).id;
    } on ApiException catch (error) {
      if (error.code == 'no_errors') return null;
      _fail(error);
      return null;
    }
  }

  List<SessionItem> _mark(SessionItem item, AttemptResult result) => [
    for (final i in state.items) i.id == item.id ? i.answeredWith(result) : i,
  ];

  void _fail(ApiException error) =>
      state = state.copyWith(phase: Phase.error, error: error.message);
}
