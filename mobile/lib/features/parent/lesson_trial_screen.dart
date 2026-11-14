import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/router.dart';
import '../../app/theme.dart';
import '../../app/widgets.dart';
import '../../core/api/api_exception.dart';
import '../../core/session.dart';
import '../../models/session.dart';
import '../../models/trial.dart';
import '../session/activities/activity_registry.dart';
import '../session/activities/common.dart';
import '../session/correction_view.dart';
import 'lesson_content_screen.dart';

/// Une erreur que le parent a notée pendant l'essai : enregistrée sur le serveur (§5.90), pour
/// être corrigée ensuite dans « Questions de la leçon ».
typedef _Noted = ({int number, String notions, String? answer, String id});

/// « Essayer la leçon » (§5.84) : le parent joue la séance que son enfant aura, voit chaque
/// correction et note ce qui est faux. Rien n'est enregistré ni compté pour l'enfant.
class LessonTrialScreen extends ConsumerStatefulWidget {
  const LessonTrialScreen({
    required this.childId,
    required this.lessonId,
    this.full = false,
    super.key,
  });

  final String childId;
  final String lessonId;

  /// Toute la leçon : chaque notion au moins une fois.
  final bool full;

  @override
  ConsumerState<LessonTrialScreen> createState() => _LessonTrialScreenState();
}

class _LessonTrialScreenState extends ConsumerState<LessonTrialScreen> {
  LessonTrial? _trial;
  List<TrialItem> _items = const [];
  int _index = 0;
  Correction? _correction;
  bool _busy = false;
  String? _error;
  int _right = 0;
  final _noted = <_Noted>[];

  @override
  void initState() {
    super.initState();
    Future.microtask(_start);
  }

  Future<void> _start() async {
    setState(() {
      _trial = null;
      _error = null;
      _index = 0;
      _right = 0;
      _correction = null;
      _noted.clear();
    });
    try {
      final trial = await ref
          .read(apiProvider)
          .startTrial(widget.childId, widget.lessonId, full: widget.full);
      if (!mounted) return;
      setState(() {
        _trial = trial;
        // Un jeu que cette version de l'application ne connaît pas est sauté, comme pour l'enfant.
        _items = [
          for (final i in trial.items)
            if (activityRegistry.containsKey(i.item.type)) i,
        ];
      });
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    }
  }

  Future<void> _submit(Map<String, Object?> response) async {
    final trial = _trial;
    if (trial == null || _busy || _correction != null) return;
    setState(() => _busy = true);
    try {
      final correction = await ref
          .read(apiProvider)
          .checkTrial(
            widget.childId,
            widget.lessonId,
            trial,
            _items[_index].item.position,
            response,
          );
      if (!mounted) return;
      setState(() {
        _correction = correction;
        if (correction.result == AttemptResult.correct) _right++;
      });
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _next() => setState(() {
    _correction = null;
    _index++;
  });

  bool get _isNoted => _noted.any((n) => n.number == _index + 1);

  Future<void> _toggleNote() async {
    final trial = _trial;
    if (trial == null || _busy) return;
    final number = _index + 1;
    final api = ref.read(apiProvider);
    setState(() => _busy = true);
    try {
      if (_noted.where((n) => n.number == number).firstOrNull case final noted?) {
        await api.resolveTrialNote(widget.childId, widget.lessonId, noted.id);
        if (mounted) setState(() => _noted.remove(noted));
      } else {
        final note = await api.noteTrial(
          widget.childId,
          widget.lessonId,
          trial,
          _items[_index].item.position,
        );
        if (mounted) {
          setState(
            () => _noted.add((
              number: number,
              notions: _items[_index].notions.join(', '),
              answer: note.answer ?? _correction?.correctAnswer,
              id: note.id,
            )),
          );
        }
      }
    } on ApiException catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(error.message)));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _back() => context.go(Routes.lessonContent(widget.childId, widget.lessonId));

  @override
  Widget build(BuildContext context) {
    final done = _trial != null && _index >= _items.length;
    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.close),
          tooltip: 'Quitter l\'essai',
          onPressed: _back,
        ),
        title: Text(
          _trial == null || done
              ? (widget.full ? 'Essai de toute la leçon' : 'Essai de la leçon')
              : 'Essai · question ${_index + 1} / ${_items.length}',
        ),
      ),
      body: CenteredBody(top: true, children: _body(done)),
    );
  }

  List<Widget> _body(bool done) {
    if (_error case final error?) {
      return [
        Text(error, style: const TextStyle(fontSize: 17)),
        const SizedBox(height: 16),
        FilledButton(onPressed: _start, child: const Text('Relancer l\'essai')),
        const SizedBox(height: 8),
        OutlinedButton(onPressed: _back, child: const Text('Retour aux questions')),
      ];
    }
    if (_trial == null) return const [Center(child: CircularProgressIndicator())];
    if (done) return _summary();
    final current = _items[_index];
    if (_correction case final correction?) {
      return [
        CorrectionView(
          item: current.item,
          correction: correction,
          onContinue: _next,
          report: OutlinedButton.icon(
            onPressed: _toggleNote,
            icon: Icon(_isNoted ? Icons.flag : Icons.flag_outlined),
            label: Text(_isNoted ? 'Erreur notée' : 'Il y a une erreur dans cette question'),
          ),
        ),
      ];
    }
    return [
      const Card(
        color: Color(0xFFFFF3E0),
        child: Padding(
          padding: EdgeInsets.all(12),
          child: Text(
            'Mode essai : vous voyez ce que l\'enfant verra. Rien n\'est compté pour lui.',
            style: TextStyle(fontSize: 15),
          ),
        ),
      ),
      const SizedBox(height: 12),
      if (current.notions.isNotEmpty) ...[
        Text(
          'Notion : ${current.notions.join(', ')}',
          style: const TextStyle(fontSize: 15, color: Colors.black54),
        ),
        const SizedBox(height: 8),
      ],
      AbsorbPointer(
        absorbing: _busy,
        child: KeyedSubtree(
          key: ValueKey(current.item.id),
          child: ActivityInstruction(
            text: current.item.instruction,
            child: activityRegistry[current.item.type]!(current.item.payload, _submit),
          ),
        ),
      ),
    ];
  }

  List<Widget> _summary() => [
    Text('Essai terminé', style: Theme.of(context).textTheme.headlineSmall),
    const SizedBox(height: 8),
    Text(
      '$_right bonne(s) réponse(s) sur ${_items.length}. Rien n\'a été compté pour l\'enfant.',
      style: const TextStyle(fontSize: 17),
    ),
    const SizedBox(height: 16),
    if (_noted.isEmpty)
      const Text(
        'Vous n\'avez noté aucune erreur. Si tout vous semble juste, validez la leçon.',
        style: TextStyle(fontSize: 16),
      )
    else ...[
      Text(
        '🚩 ${_noted.length} erreur(s) notée(s), à corriger avant de valider. Elles vous '
        'attendent dans « Questions de la leçon », sur chaque notion :',
        style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700),
      ),
      const SizedBox(height: 8),
      for (final note in _noted)
        Card(
          child: ListTile(
            leading: const Icon(Icons.flag, color: LudiColors.notMastered),
            title: Text(
              note.notions.isEmpty
                  ? 'Question ${note.number}'
                  : 'Question ${note.number} · ${note.notions}',
            ),
            subtitle: note.answer == null
                ? null
                : Text('Réponse donnée pour juste : ${note.answer}'),
          ),
        ),
    ],
    if (_trial case LessonTrial(full: true, :final neverShown) when neverShown.isNotEmpty) ...[
      const SizedBox(height: 12),
      Text(
        'Pas dans l\'essai, ni dans les séances de l\'enfant (notions secondaires, la leçon en a '
        'assez d\'importantes) : ${neverShown.join(', ')}.',
        style: const TextStyle(fontSize: 15, color: Colors.black54),
      ),
    ],
    const SizedBox(height: 16),
    FilledButton.icon(
      onPressed: () {
        ref.invalidate(lessonContentProvider((widget.childId, widget.lessonId)));
        _back();
      },
      icon: const Icon(Icons.edit_outlined),
      label: Text(_noted.isEmpty ? 'Retour aux questions' : 'Corriger les questions'),
    ),
    const SizedBox(height: 8),
    OutlinedButton.icon(
      onPressed: _start,
      icon: const Icon(Icons.refresh),
      label: const Text('Refaire un essai (autres exercices)'),
    ),
    if (!widget.full) ...[
      const SizedBox(height: 8),
      OutlinedButton.icon(
        onPressed: () =>
            context.go(Routes.lessonTrial(widget.childId, widget.lessonId, full: true)),
        icon: const Icon(Icons.playlist_play),
        label: const Text('Essayer toute la leçon (chaque notion)'),
      ),
    ],
  ];
}
