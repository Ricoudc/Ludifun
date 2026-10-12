import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/router.dart';
import '../../app/theme.dart';
import '../../app/widgets.dart';
import '../../core/session.dart';
import '../../core/sounds.dart';
import '../../models/session.dart';
import '../home/home_providers.dart';
import '../report/report_view.dart';
import 'activities/activity_registry.dart';
import 'activities/common.dart';
import 'cheers.dart';
import 'correction_view.dart';
import 'help_sheet.dart';
import 'report_question.dart';
import 'session_controller.dart';

/// Écrans 5 (jeu), 6 (correction) et 7 (bilan), dans une seule route.
class SessionScreen extends ConsumerWidget {
  const SessionScreen({required this.sessionId, super.key});

  final String sessionId;

  bool _playing(SessionState state) => switch (state.phase) {
    Phase.question || Phase.submitting || Phase.correction => true,
    _ => false,
  };

  /// Quitter en cours de séance demande une confirmation ; la séance reste reprenable.
  Future<void> _leave(BuildContext context, WidgetRef ref, SessionState state) async {
    if (_playing(state)) {
      final stop = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('Tu veux faire une pause ?'),
          content: const Text('Tu pourras reprendre ta séance plus tard, depuis l\'accueil.'),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('Arrêter'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(context).pop(false),
              style: FilledButton.styleFrom(minimumSize: const Size(120, 48)),
              child: const Text('Continuer'),
            ),
          ],
        ),
      );
      if (stop != true) return;
    }
    refreshHome(ref);
    if (context.mounted) context.go(Routes.childHome);
  }

  Future<void> _reviewErrors(BuildContext context, WidgetRef ref) async {
    final id = await ref.read(sessionControllerProvider(sessionId).notifier).reviewErrors();
    if (!context.mounted) return;
    if (id != null) {
      context.go(Routes.session(id));
    } else if (ref.read(sessionControllerProvider(sessionId)).phase != Phase.error) {
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('Aucune erreur à revoir : bravo !')));
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // Sons : la correction (juste, presque, pas tout à fait) et la fin de la séance.
    ref.listen(sessionControllerProvider(sessionId), (previous, next) {
      if (previous?.phase == next.phase) return;
      final sounds = ref.read(soundsProvider);
      switch (next.phase) {
        case Phase.correction:
          sounds.play(switch (next.correction?.result) {
            AttemptResult.correct => Sound.correct,
            AttemptResult.partial => Sound.partial,
            _ => Sound.wrong,
          });
        case Phase.report:
          sounds.play(Sound.finish);
        default:
          break;
      }
    });
    final state = ref.watch(sessionControllerProvider(sessionId));
    final controller = ref.read(sessionControllerProvider(sessionId).notifier);
    final (index, total) = state.counter;
    final item = state.current;
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _leave(context, ref, state);
      },
      child: Scaffold(
        appBar: AppBar(
          leading: CloseButton(onPressed: () => _leave(context, ref, state)),
          title: _playing(state)
              ? Text(
                  state.inReplay
                      ? '🔄 Reprise des erreurs $index / $total'
                      : state.inBonus
                      ? '🚀 Défi bonus $index / $total'
                      : 'Question $index / $total',
                )
              : null,
          actions: [
            if (_playing(state) && state.stars > 0)
              Center(
                child: Padding(
                  padding: const EdgeInsets.only(right: 4),
                  child: Text(
                    '⭐ ${state.stars}',
                    key: const Key('stars-counter'),
                    style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800),
                  ),
                ),
              ),
            IconButton(
              tooltip: ref.watch(soundOnProvider).value ?? true
                  ? 'Couper le son'
                  : 'Remettre le son',
              icon: Icon(
                ref.watch(soundOnProvider).value ?? true ? Icons.volume_up : Icons.volume_off,
              ),
              onPressed: () => ref.read(soundOnProvider.notifier).toggle(),
            ),
          ],
          bottom: _playing(state) && !state.inReplay && !state.inBonus
              ? PreferredSize(
                  preferredSize: const Size.fromHeight(8),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    child: LinearProgressIndicator(
                      value: state.progress,
                      minHeight: 8,
                      borderRadius: BorderRadius.circular(4),
                    ),
                  ),
                )
              : null,
        ),
        bottomNavigationBar: state.phase == Phase.report && state.report != null
            ? ReportActions(
                report: state.report!,
                onReviewErrors: () => _reviewErrors(context, ref),
                onDone: () => _leave(context, ref, state),
              )
            : null,
        body: CenteredBody(
          top: _playing(state) || state.phase == Phase.report,
          children: [
            switch (state.phase) {
              Phase.loading => const Center(child: CircularProgressIndicator()),
              Phase.completing => const _Waiting('On prépare ton bilan…'),
              Phase.question || Phase.submitting when item != null => Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (state.offline) ...[
                    const Card(
                      color: Color(0xFFFFF3E0),
                      child: Padding(
                        padding: EdgeInsets.all(12),
                        child: Text(
                          '📴 Sans Internet : tes réponses sont gardées, elles seront corrigées '
                          'quand tu retrouveras le réseau.',
                          style: TextStyle(fontSize: 15),
                        ),
                      ),
                    ),
                    const SizedBox(height: 8),
                  ],
                  if (state.missionStep case (final step, final steps, final label)) ...[
                    Text(
                      '🚀 Étape $step / $steps · $label',
                      style: const TextStyle(fontSize: 16, color: LudiColors.primary),
                    ),
                    const SizedBox(height: 8),
                  ],
                  if (item.daily case final name?) ...[
                    DailyGameBanner(name),
                    const SizedBox(height: 12),
                  ],
                  if (item.intro case final intro?) ...[
                    Card(
                      color: LudiColors.primary.withValues(alpha: 0.08),
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Text(intro, style: const TextStyle(fontSize: 18, height: 1.35)),
                      ),
                    ),
                    const SizedBox(height: 16),
                  ],
                  AbsorbPointer(
                    absorbing: state.phase == Phase.submitting,
                    child: KeyedSubtree(
                      key: ValueKey(item.id),
                      child: ActivityInstruction(
                        text: item.instruction,
                        child: activityRegistry[item.type]!(item.payload, controller.submit),
                      ),
                    ),
                  ),
                  if (item.helpAvailable && state.phase == Phase.question && !state.offline) ...[
                    const SizedBox(height: 12),
                    TextButton(
                      onPressed: () => showHelp(context, sessionId, item.id),
                      child: const Text('❓ Je n\'ai pas compris'),
                    ),
                  ],
                ],
              ),
              Phase.correction when item != null && state.correction != null => CorrectionView(
                item: item,
                correction: state.correction!,
                stars: starsFor(state.correction!.score),
                streak: state.streak,
                onStar: () => ref.read(soundsProvider).play(Sound.star),
                onContinue: controller.next,
                report: ReportQuestionButton(
                  key: ValueKey(item.id),
                  sessionId: sessionId,
                  itemId: item.id,
                ),
                onPause: () {
                  refreshHome(ref);
                  context.go(Routes.childHome);
                },
              ),
              Phase.bonusOffer => Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Text('🚀', textAlign: TextAlign.center, style: TextStyle(fontSize: 56)),
                  const SizedBox(height: 8),
                  Text(
                    'Tu as été rapide et tu as tout réussi !',
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.headlineSmall,
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    'Encore 3 défis bonus, un peu plus difficiles ? Ils ne comptent pas dans ta note.',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 18),
                  ),
                  const SizedBox(height: 24),
                  FilledButton(
                    style: FilledButton.styleFrom(backgroundColor: LudiColors.accent),
                    onPressed: controller.acceptBonus,
                    child: const Text('Oui, j\'y vais !'),
                  ),
                  const SizedBox(height: 12),
                  OutlinedButton(
                    onPressed: controller.declineBonus,
                    child: const Text('Non, j\'ai fini'),
                  ),
                ],
              ),
              Phase.report when state.report != null => ReportView(
                report: state.report!,
                stars: state.stars,
                bestStreak: state.bestStreak,
                onRate: (rating) => ref
                    .read(apiProvider)
                    .sendFeedback(rating: rating, screen: 'report', sessionId: sessionId),
              ),
              Phase.savedOffline => Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Text(
                    '📴 Bravo, tu as fini ta séance !\n\nElle est gardée sur ton téléphone : elle '
                    'sera corrigée dès que tu retrouveras Internet, et tu verras ton bilan sur '
                    'l\'accueil.',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 19, height: 1.35),
                  ),
                  const SizedBox(height: 20),
                  FilledButton(
                    onPressed: () => _leave(context, ref, state),
                    child: const Text('Retour à l\'accueil'),
                  ),
                ],
              ),
              Phase.error => Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  ErrorMessage(state.error ?? 'Petit souci de notre côté, réessaie.'),
                  const SizedBox(height: 16),
                  FilledButton(onPressed: controller.load, child: const Text('Réessayer')),
                ],
              ),
              _ => Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Text(
                    'Cette séance est déjà terminée. 👍',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 20),
                  ),
                  const SizedBox(height: 16),
                  FilledButton(
                    onPressed: () => _leave(context, ref, state),
                    child: const Text('Retour à l\'accueil'),
                  ),
                ],
              ),
            },
          ],
        ),
      ),
    );
  }
}

class _Waiting extends StatelessWidget {
  const _Waiting(this.text);

  final String text;

  @override
  Widget build(BuildContext context) => Column(
    children: [
      const CircularProgressIndicator(),
      const SizedBox(height: 16),
      Text(text, style: const TextStyle(fontSize: 18)),
    ],
  );
}
