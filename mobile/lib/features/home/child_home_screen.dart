import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/format.dart';
import '../../app/router.dart';
import '../../app/theme.dart';
import '../../app/widgets.dart';
import '../../core/api/api_exception.dart';
import '../../core/app_update.dart';
import '../../core/offline.dart';
import '../../core/session.dart';
import '../../core/storage/credentials.dart';
import '../../models/lesson.dart';
import '../../models/subject.dart';
import '../rewards/progress_strip.dart';
import 'home_providers.dart';

/// Écran 1 : mission du jour, nouvelle leçon, dernières révisions.
class ChildHomeScreen extends ConsumerWidget {
  const ChildHomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final stored = switch (ref.watch(sessionProvider).value) {
      ChildCredentials(:final displayName) => displayName,
      _ => '',
    };
    final name = ref.watch(meProvider).value?.displayName ?? stored;
    final lessons = ref.watch(lessonsProvider);
    return Scaffold(
      body: RefreshIndicator(
        onRefresh: () async {
          refreshHome(ref);
          await ref.read(lessonsProvider.future);
        },
        child: CenteredBody(
          top: true,
          children: [
            Text('Bonjour $name ! 👋', style: Theme.of(context).textTheme.headlineMedium),
            const SizedBox(height: 12),
            if (ref.watch(progressProvider).value case final progress?) ...[
              ProgressStrip(progress, onBadges: () => context.go(Routes.badges)),
              const SizedBox(height: 12),
            ] else
              const SizedBox(height: 8),
            const AppUpdateBanner(forChild: true),
            const OfflineSessionsCard(),
            const _MissionCard(),
            const SizedBox(height: 16),
            OutlinedButton.icon(
              onPressed: () => context.go(Routes.capture),
              icon: const Icon(Icons.add_a_photo_outlined),
              label: const Text('Nouvelle leçon', style: TextStyle(fontSize: 18)),
            ),
            const SizedBox(height: 8),
            OutlinedButton.icon(
              onPressed: () => context.go(Routes.homeworkStart),
              icon: const Icon(Icons.edit_note),
              label: const Text('Aide aux devoirs', style: TextStyle(fontSize: 18)),
            ),
            const SizedBox(height: 8),
            OutlinedButton.icon(
              onPressed: () => context.go(Routes.notebook),
              icon: const Icon(Icons.menu_book_outlined),
              label: const Text('Mon cahier', style: TextStyle(fontSize: 18)),
            ),
            const SizedBox(height: 28),
            ...switch (lessons) {
              AsyncData(value: final list) when list.isEmpty => [const _EmptyState()],
              AsyncData(value: final list) => [
                Text('Mes dernières révisions', style: Theme.of(context).textTheme.titleLarge),
                const SizedBox(height: 12),
                for (final lesson in list) ...[_LessonRow(lesson), const SizedBox(height: 8)],
              ],
              AsyncError(:final error) => [
                ErrorMessage(error is ApiException ? error.message : ApiException.unexpected),
                TextButton(onPressed: () => refreshHome(ref), child: const Text('Réessayer')),
              ],
              _ => [const Center(child: CircularProgressIndicator())],
            },
          ],
        ),
      ),
    );
  }
}

class _MissionCard extends ConsumerWidget {
  const _MissionCard();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final white = Theme.of(context).textTheme.titleLarge?.copyWith(color: Colors.white);
    final state = ref.watch(missionProvider);
    final mission = state.value;
    final lessonId = mission?.lessonId;
    return Card(
      color: LudiColors.primary,
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('🎯 Ta mission du jour', style: white),
            const SizedBox(height: 10),
            if (state.hasError && mission == null)
              const Text(
                'Photographie une leçon pour commencer.',
                style: TextStyle(color: Colors.white, fontSize: 18),
              )
            else if (mission == null)
              const LinearProgressIndicator(color: Colors.white)
            else if (lessonId == null)
              const Text(
                '🎉 Tout est à jour ! Photographie une nouvelle leçon.',
                style: TextStyle(color: Colors.white, fontSize: 18),
              )
            else ...[
              if (mission.examTitle != null && mission.examDate != null) ...[
                Text(
                  '📅 ${mission.examTitle} ${dayLabel(mission.examDate!, ref.watch(nowProvider)())}',
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                if (mission.focusLabel != null)
                  Text(
                    mission.focusLabel!,
                    style: const TextStyle(color: Colors.white, fontSize: 16),
                  ),
                const SizedBox(height: 8),
              ],
              Text(
                '${Subjects.emoji(mission.subject)} ${mission.title ?? 'Ta leçon'}'
                '${mission.estimatedMinutes == null ? '' : ' · ⏱️ ${mission.estimatedMinutes} min'}',
                style: const TextStyle(color: Colors.white, fontSize: 18),
              ),
              const SizedBox(height: 14),
              FilledButton(
                style: FilledButton.styleFrom(
                  backgroundColor: LudiColors.accent,
                  foregroundColor: Colors.black,
                ),
                onPressed: () => context.go(Routes.lesson(lessonId)),
                child: const Text('Commencer'),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState();

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 24),
    child: Column(
      children: [
        const Text('📸', style: TextStyle(fontSize: 64)),
        const SizedBox(height: 8),
        Text(
          'Photographie ta première leçon !',
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.titleLarge,
        ),
      ],
    ),
  );
}

class _LessonRow extends ConsumerWidget {
  const _LessonRow(this.lesson);

  final LessonSummary lesson;

  Future<void> _open(BuildContext context, WidgetRef ref) async {
    switch (lesson.status) {
      case LessonStatus.ready:
        context.go(Routes.lesson(lesson.id));
      case LessonStatus.failed:
        await _retry(context, ref);
      case _:
        context.go(Routes.analysis(lesson.id));
    }
  }

  /// Une erreur de l'IA se relance sans nouvelle photo ; sinon, il faut reprendre la photo.
  Future<void> _retry(BuildContext context, WidgetRef ref) async {
    final api = ref.read(apiProvider);
    try {
      final detail = await api.lesson(lesson.id);
      if (!context.mounted) return;
      if (detail.canRetry) {
        await api.retryLesson(lesson.id);
        if (context.mounted) context.go(Routes.analysis(lesson.id));
      } else {
        await api.deleteLesson(lesson.id);
        if (context.mounted) context.go(Routes.capture);
      }
    } on ApiException catch (error) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(error.message)));
      }
    }
  }

  Future<void> _delete(BuildContext context, WidgetRef ref) async {
    final confirmed = await showModalBottomSheet<bool>(
      context: context,
      builder: (context) => SafeArea(
        child: ListTile(
          leading: const Icon(Icons.delete_outline, color: LudiColors.notMastered),
          title: const Text('Supprimer cette leçon'),
          onTap: () => Navigator.of(context).pop(true),
        ),
      ),
    );
    if (confirmed != true) return;
    try {
      await ref.read(apiProvider).deleteLesson(lesson.id);
    } on ApiException catch (error) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(error.message)));
      }
    }
    refreshHome(ref);
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // Une leçon prête : l'état sous le titre, pour que le titre garde toute la largeur.
    final (String title, Widget? status, Widget trailing) = switch (lesson.status) {
      LessonStatus.failed => (
        'Leçon non analysée',
        null,
        const Chip(label: Text('Réessayer'), avatar: Icon(Icons.refresh, size: 18)),
      ),
      LessonStatus.needsReview => (
        'Un mot à vérifier',
        null,
        const Chip(label: Text('Vérifier'), avatar: Icon(Icons.search, size: 18)),
      ),
      LessonStatus.ready => (
        lesson.title ?? 'Leçon',
        Text(
          reviewLabel(lesson, ref.watch(nowProvider)()),
          style: TextStyle(
            fontSize: 15,
            color: lesson.mastered && !lesson.due ? LudiColors.mastered : null,
            fontWeight: lesson.due ? FontWeight.w700 : null,
          ),
        ),
        const Icon(Icons.chevron_right),
      ),
      _ => (
        'Analyse en cours…',
        null,
        const SizedBox.square(dimension: 20, child: CircularProgressIndicator(strokeWidth: 2)),
      ),
    };
    return Card(
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
        leading: Text(Subjects.emoji(lesson.subject), style: const TextStyle(fontSize: 28)),
        title: Text(title, style: const TextStyle(fontWeight: FontWeight.w600)),
        subtitle: status,
        trailing: trailing,
        onTap: () => _open(context, ref),
        // Seule une leçon ratée se retire ici ; les autres, c'est le parent qui les supprime.
        onLongPress: lesson.status == LessonStatus.failed ? () => _delete(context, ref) : null,
      ),
    );
  }
}

/// Séances gardées pour jouer sans Internet : à jouer, ou en attente d'envoi. À l'ouverture de
/// l'accueil, les réponses en attente partent ; le bilan des séances finies est annoncé.
class OfflineSessionsCard extends ConsumerStatefulWidget {
  const OfflineSessionsCard({super.key});

  @override
  ConsumerState<OfflineSessionsCard> createState() => _OfflineSessionsCardState();
}

class _OfflineSessionsCardState extends ConsumerState<OfflineSessionsCard> {
  List<SyncedSession> _synced = const [];
  bool _syncing = false;

  @override
  void initState() {
    super.initState();
    Future.microtask(_sync);
  }

  Future<void> _sync() async {
    if (_syncing) return;
    _syncing = true;
    try {
      final synced = await ref.read(offlineSessionsProvider).sync();
      if (!mounted || synced.isEmpty) return;
      setState(() => _synced = [..._synced, ...synced]);
      refreshHome(ref);
    } finally {
      _syncing = false;
    }
  }

  @override
  Widget build(BuildContext context) {
    // Les leçons arrivent : Internet est là, ce qui attend part (l'accueil reste ouvert sous la
    // séance, il n'est pas reconstruit au retour).
    ref.listen(lessonsProvider, (_, next) {
      if (next.hasValue && !next.isLoading) Future.microtask(_sync);
    });
    final packs = ref.watch(offlinePacksProvider).value ?? const <OfflinePack>[];
    if (packs.isEmpty && _synced.isEmpty) return const SizedBox();
    return Card(
      margin: const EdgeInsets.only(bottom: 16),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            for (final done in _synced)
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Text(
                  '✅ Ta séance « ${done.lessonTitle ?? 'sans Internet'} » est corrigée : '
                  '${score(done.scoreOn10)} / 10',
                  style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w600),
                ),
              ),
            if (packs.isNotEmpty) ...[
              Text('📴 Pour jouer sans Internet', style: Theme.of(context).textTheme.titleMedium),
              for (final pack in packs)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(pack.lessonTitle ?? 'Séance gardée'),
                  subtitle: Text(
                    pack.finished
                        ? 'Finie : sera corrigée au retour d\'Internet'
                        : pack.answers.isEmpty
                        ? 'Prête à jouer'
                        : '${pack.answers.length} réponse(s) gardée(s), à finir',
                  ),
                  trailing: pack.finished
                      ? const Icon(Icons.cloud_upload_outlined)
                      : const Icon(Icons.play_arrow),
                  onTap: pack.finished ? _sync : () => context.go(Routes.session(pack.sessionId)),
                ),
            ],
          ],
        ),
      ),
    );
  }
}
