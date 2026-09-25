import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/router.dart';
import '../../app/theme.dart';
import '../../app/widgets.dart';
import '../../core/api/api_exception.dart';
import '../../core/session.dart';
import '../../models/lesson.dart';
import '../capture/capture_controller.dart';
import '../home/home_providers.dart';
import 'review_form.dart';
import 'step_pacer.dart';

const pollInterval = Duration(milliseconds: 1500);
const readyPause = Duration(milliseconds: 900);

/// Au-delà, l'écran explique l'attente : une IA installée sur un ordinateur sans carte
/// graphique peut mettre de longues minutes à lire une photo.
const slowAfter = Duration(minutes: 1);

const _stepLabels = {
  'reading': ('🔎', 'Lecture de ta leçon…'),
  'analyzing': ('🧠', 'Identification des notions…'),
  'generating': ('🎮', 'Préparation de tes exercices…'),
};

/// Écran 3 : suit l'analyse (`GET /v1/lessons/{id}` toutes les 1,5 s).
class AnalysisScreen extends ConsumerStatefulWidget {
  const AnalysisScreen({required this.lessonId, this.childId, super.key});

  final String lessonId;

  /// Leçon déposée par le parent pour cet enfant.
  final String? childId;

  String get home => childId == null ? Routes.childHome : Routes.childDashboard(childId!);

  @override
  ConsumerState<AnalysisScreen> createState() => _AnalysisScreenState();
}

class _AnalysisScreenState extends ConsumerState<AnalysisScreen> {
  var _pacer = StepPacer();
  Timer? _poll;
  Timer? _pace;
  Lesson? _lesson;
  bool _offline = false;
  bool _leaving = false;
  late DateTime _startedAt = ref.read(nowProvider)();

  @override
  void initState() {
    super.initState();
    _start();
  }

  void _start() {
    _poll?.cancel();
    _pace?.cancel();
    _pacer = StepPacer();
    _lesson = null;
    _startedAt = ref.read(nowProvider)();
    _fetch();
    _poll = Timer.periodic(pollInterval, (_) => _fetch());
    _pace = Timer.periodic(StepPacer.minStep, (_) => _advance());
  }

  @override
  void dispose() {
    _poll?.cancel();
    _pace?.cancel();
    super.dispose();
  }

  /// Une seule interrogation à la fois : sur un serveur ralenti (IA locale), une réponse
  /// ancienne (« en cours ») arrivée après « prête » figeait l'écran, l'interrogation étant
  /// déjà arrêtée.
  bool _fetching = false;

  Future<void> _fetch() async {
    if (_fetching) return;
    _fetching = true;
    try {
      final lesson = await ref.read(apiProvider).lesson(widget.lessonId, childId: widget.childId);
      if (!mounted) return;
      if (!lesson.status.inProgress) _poll?.cancel(); // prête, en échec, ou à vérifier
      _pacer.serverDone(lesson.stepsDone);
      setState(() {
        _lesson = lesson;
        _offline = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      if (error.status == 404) {
        _poll?.cancel();
        context.go(widget.home);
        return;
      }
      setState(() => _offline = true); // on continue d'interroger
    } finally {
      _fetching = false;
    }
  }

  void _advance() {
    if (_pacer.tick()) setState(() {});
    if (_pacer.finished && _lesson?.status == LessonStatus.ready && !_leaving) {
      _leaving = true;
      _pace?.cancel();
      // Les photos de cette leçon quittent le téléphone (§15) ; pas celles d'une autre.
      ref.read(captureProvider.notifier).analysisFinished(widget.lessonId);
      refreshHome(ref);
      Timer(readyPause, () {
        if (!mounted) return;
        if (widget.childId == null) {
          context.go(Routes.lesson(widget.lessonId));
        } else {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Leçon prête : elle apparaît dans la mission du jour.')),
          );
          context.go(widget.home);
        }
      });
    }
  }

  /// « Peux-tu vérifier ? » envoyé : l'analyse reprend sur le texte corrigé.
  Future<void> _sendReview(List<ReviewAnswer> answers) async {
    try {
      await ref.read(apiProvider).reviewLesson(widget.lessonId, answers, childId: widget.childId);
      if (mounted) setState(_start);
    } on ApiException catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(error.message)));
      }
    }
  }

  Future<void> _retry() async {
    try {
      await ref.read(apiProvider).retryLesson(widget.lessonId, childId: widget.childId);
      if (mounted) setState(_start);
    } on ApiException catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(error.message)));
      }
    }
  }

  /// Retour à l'écran 2 : les photos sont encore sur le téléphone ; la leçon ratée disparaît.
  Future<void> _retake() async {
    try {
      await ref.read(apiProvider).deleteLesson(widget.lessonId, childId: widget.childId);
    } on ApiException {
      // sans importance : la leçon ratée reste simplement dans la liste
    }
    refreshHome(ref);
    if (mounted) {
      context.go(widget.childId == null ? Routes.capture : Routes.childCapture(widget.childId!));
    }
  }

  @override
  Widget build(BuildContext context) {
    final lesson = _lesson;
    final failed = lesson?.status == LessonStatus.failed;
    final ready = _leaving;
    return Scaffold(
      appBar: AppBar(leading: CloseButton(onPressed: () => context.go(widget.home))),
      body: CenteredBody(
        children: [
          for (final (i, step) in analysisSteps.indexed)
            _StepRow(
              emoji: _stepLabels[step]!.$1,
              label: _stepLabels[step]!.$2,
              state: _pacer.stateOf(i, failed: failed),
            ),
          const SizedBox(height: 32),
          if (ready)
            Text(
              'C\'est prêt ! 🎉',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.headlineMedium,
            )
          else if (failed)
            ..._failure(lesson!)
          else if (lesson != null && lesson.status == LessonStatus.needsReview)
            ReviewForm(
              key: ValueKey(lesson.review.map((i) => i.id).join()),
              items: lesson.review,
              photos: [for (final page in ref.watch(captureProvider)) page.bytes],
              onSubmit: _sendReview,
            )
          else if (lesson == null || lesson.status.inProgress)
            ..._waiting(),
          if (lesson?.diagnostics case final Diagnostics d
              when d.steps.isNotEmpty || d.explanation != null) ...[
            const SizedBox(height: 16),
            DiagnosticsPanel(diagnostics: d, failed: failed),
          ],
          if (_offline)
            const Text(
              'Connexion perdue… je réessaie.',
              textAlign: TextAlign.center,
              style: TextStyle(color: Colors.black54),
            ),
        ],
      ),
    );
  }

  /// Longue attente : le temps écoulé, pourquoi, et qu'on peut fermer sans rien perdre.
  List<Widget> _waiting() {
    final elapsed = ref.read(nowProvider)().difference(_startedAt);
    if (elapsed < slowAfter) return const [];
    return [
      Text(
        '⏳ ${elapsed.inMinutes} min',
        textAlign: TextAlign.center,
        style: Theme.of(context).textTheme.titleLarge,
      ),
      const SizedBox(height: 8),
      const Text(
        'L\'intelligence artificielle travaille. Avec une IA installée sur un ordinateur sans '
        'carte graphique, cela peut prendre de 10 à 30 minutes.\n\nTu peux fermer : la leçon '
        'continue d\'être préparée et apparaîtra sur ton accueil.',
        textAlign: TextAlign.center,
        style: TextStyle(fontSize: 16, color: Colors.black54, height: 1.35),
      ),
      const SizedBox(height: 12),
    ];
  }

  List<Widget> _failure(Lesson lesson) {
    final hasPhotos = ref.watch(captureProvider).isNotEmpty;
    return [
      ErrorMessage(lesson.failureMessage ?? ApiException.unexpected),
      const SizedBox(height: 24),
      if (lesson.canRetry)
        FilledButton(onPressed: _retry, child: const Text('Réessayer'))
      else
        FilledButton(
          onPressed: _retake,
          child: Text(hasPhotos ? 'Reprendre la photo' : 'Prendre une photo'),
        ),
      const SizedBox(height: 12),
      TextButton(
        onPressed: () => context.go(widget.home),
        child: const Text('Retour à l\'accueil'),
      ),
    ];
  }
}

class _StepRow extends StatelessWidget {
  const _StepRow({required this.emoji, required this.label, required this.state});

  final String emoji;
  final String label;
  final AnalysisStep state;

  @override
  Widget build(BuildContext context) => AnimatedOpacity(
    opacity: state == AnalysisStep.pending ? 0.35 : 1,
    duration: const Duration(milliseconds: 300),
    child: Padding(
      padding: const EdgeInsets.symmetric(vertical: 12),
      child: Row(
        children: [
          Text(emoji, style: const TextStyle(fontSize: 30)),
          const SizedBox(width: 14),
          Expanded(child: Text(label, style: const TextStyle(fontSize: 19))),
          SizedBox.square(
            dimension: 28,
            child: switch (state) {
              AnalysisStep.done => const Icon(Icons.check_circle, color: LudiColors.mastered),
              AnalysisStep.running => const CircularProgressIndicator(strokeWidth: 3),
              AnalysisStep.pending => const SizedBox(),
            },
          ),
        ],
      ),
    ),
  );
}

/// « Voir ce qui se passe » : chaque étape de l'IA (modèle, durée, résultat) et, en cas d'échec,
/// la raison en clair puis le message de l'IA. Ouvert d'emblée quand l'analyse a échoué.
class DiagnosticsPanel extends StatelessWidget {
  const DiagnosticsPanel({required this.diagnostics, required this.failed, super.key});

  final Diagnostics diagnostics;
  final bool failed;

  static String duration(int seconds) => seconds < 60
      ? '$seconds s'
      : '${seconds ~/ 60} min ${(seconds % 60).toString().padLeft(2, '0')}';

  @override
  Widget build(BuildContext context) => Card(
    margin: EdgeInsets.zero,
    child: ExpansionTile(
      key: ValueKey('diagnostics-$failed'),
      initiallyExpanded: failed,
      leading: const Icon(Icons.manage_search),
      title: const Text('Voir ce qui se passe'),
      childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
      expandedCrossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (diagnostics.explanation case final explanation?)
          Container(
            margin: const EdgeInsets.only(bottom: 8),
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: LudiColors.notMastered.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Text('Pourquoi ? $explanation', style: const TextStyle(fontSize: 15)),
          ),
        for (final step in diagnostics.steps)
          ListTile(
            dense: true,
            contentPadding: EdgeInsets.zero,
            leading: step.running
                ? const SizedBox.square(
                    dimension: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : Icon(
                    step.ok ? Icons.check_circle : Icons.error,
                    color: step.ok ? LudiColors.mastered : LudiColors.notMastered,
                  ),
            title: Text('${step.stage} · ${step.model}'),
            subtitle: step.message == null
                ? null
                : Text(step.message!, style: const TextStyle(fontSize: 12)),
            trailing: Text(
              step.running ? 'depuis ${duration(step.seconds)}' : duration(step.seconds),
            ),
          ),
      ],
    ),
  );
}
