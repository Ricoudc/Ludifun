import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/format.dart';
import '../../app/ludi_mascot.dart';
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
            _WelcomeCard(name: name),
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
            Text('À toi de choisir', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 12),
            LayoutBuilder(
              builder: (context, constraints) {
                final tileWidth = (constraints.maxWidth - 12) / 2;
                return Wrap(
                  spacing: 12,
                  runSpacing: 12,
                  children: [
                    _HomeActionTile(
                      width: tileWidth,
                      title: 'Nouvelle leçon',
                      description: 'Photographie ton cahier',
                      icon: Icons.add_a_photo_outlined,
                      route: Routes.capture,
                      tint: const Color(0xFFE5F2FF),
                    ),
                    _HomeActionTile(
                      width: tileWidth,
                      title: 'Aide aux devoirs',
                      description: 'Avance pas à pas',
                      icon: Icons.edit_note,
                      route: Routes.homeworkStart,
                      tint: const Color(0xFFE5F6F1),
                    ),
                    _HomeActionTile(
                      width: tileWidth,
                      title: 'Mon cahier',
                      description: 'Retrouve tes leçons',
                      icon: Icons.menu_book_outlined,
                      route: Routes.notebook,
                      tint: const Color(0xFFFFF3D9),
                    ),
                  ],
                );
              },
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

/// En-tête enfant : identité de Ludi et message positif, sans détourner l'attention.
class _WelcomeCard extends StatelessWidget {
  const _WelcomeCard({required this.name});

  final String name;

  @override
  Widget build(BuildContext context) => Card(
    clipBehavior: Clip.antiAlias,
    color: LudiColors.primary,
    child: Padding(
      padding: const EdgeInsets.fromLTRB(18, 14, 12, 14),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Bonjour $name ! 👋',
                  style: Theme.of(context).textTheme.titleLarge
                      ?.copyWith(color: Colors.white, fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 5),
                const Text(
                  'Prêt·e pour une nouvelle aventure ?',
                  style: TextStyle(color: Colors.white, fontSize: 14, height: 1.3),
                ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          const LudiMascot(size: 88),
        ],
      ),
    ),
  );
}

/// Tuile compacte en grille : les trois chemins principaux sont visibles sans longue liste.
class _HomeActionTile extends StatelessWidget {
  const _HomeActionTile({
    required this.width,
    required this.title,
    required this.description,
    required this.icon,
    required this.route,
    required this.tint,
  });

  final double width;
  final String title;
  final String description;
  final IconData icon;
  final String route;
  final Color tint;

  @override
  Widget build(BuildContext context) => SizedBox(
    width: width,
    height: 146,
    child: Card(
      color: Colors.white,
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () => context.go(route),
        child: Padding(
          padding: const EdgeInsets.all(13),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(color: tint, borderRadius: BorderRadius.circular(13)),
                alignment: Alignment.center,
                child: Icon(icon, color: LudiColors.primary, size: 22),
              ),
              const Spacer(),
              Text(
                title,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontSize: 15, height: 1.15, fontWeight: FontWeight.w800),
              ),
              const SizedBox(height: 3),
              Row(
                children: [
                  Expanded(
                    child: Text(
                      description,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontSize: 12, color: Color(0xFF59677D)),
                    ),
                  ),
                  const Icon(Icons.arrow_forward_rounded, size: 16, color: LudiColors.primary),
                ],
              ),
            ],
          ),
        ),
      ),
    ),
  );
}

class _MissionCard extends ConsumerWidget {
  const _MissionCard();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(missionProvider);
    final mission = state.value;
    final lessonId = mission?.lessonId;
    const ink = Color(0xFF20304A);
    return Card(
      color: const Color(0xFFEAF2FF),
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                const Icon(Icons.flag_rounded, color: LudiColors.primary, size: 20),
                const SizedBox(width: 8),
                Text(
                  '🎯 Ta mission du jour',
                  style: Theme.of(context).textTheme.labelLarge?.copyWith(
                    color: LudiColors.primary,
                    fontWeight: FontWeight.w900,
                    letterSpacing: 0.7,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            if (state.hasError && mission == null)
              const Text(
                'Photographie une leçon pour commencer.',
                style: TextStyle(color: ink, fontSize: 16, height: 1.35),
              )
            else if (mission == null)
              const LinearProgressIndicator(color: LudiColors.primary)
            else if (lessonId == null)
              const Text(
                '🎉 Tout est à jour ! Photographie une nouvelle leçon.',
                style: TextStyle(color: ink, fontSize: 16, height: 1.35),
              )
            else ...[
              if (mission.examTitle != null && mission.examDate != null) ...[
                Text(
                  '📅 ${mission.examTitle} ${dayLabel(mission.examDate!, ref.watch(nowProvider)())}',
                  style: const TextStyle(color: ink, fontSize: 14, fontWeight: FontWeight.w700),
                ),
                if (mission.focusLabel != null)
                  Text(mission.focusLabel!, style: const TextStyle(color: ink, fontSize: 14)),
                const SizedBox(height: 8),
              ],
              Text(
                '${Subjects.emoji(mission.subject)} ${mission.title ?? 'Ta leçon'}',
                style: const TextStyle(color: ink, fontSize: 19, fontWeight: FontWeight.w800),
              ),
              if (mission.estimatedMinutes != null) ...[
                const SizedBox(height: 5),
                Text(
                  'Environ ${mission.estimatedMinutes} minutes',
                  style: const TextStyle(color: Color(0xFF59677D), fontSize: 13),
                ),
              ],
              const SizedBox(height: 14),
              FilledButton.icon(
                style: FilledButton.styleFrom(
                  backgroundColor: LudiColors.primary,
                  foregroundColor: Colors.white,
                  minimumSize: const Size.fromHeight(48),
                ),
                onPressed: () => context.go(Routes.lesson(lessonId)),
                icon: const Icon(Icons.play_arrow_rounded),
                label: const Text('Commencer ma mission'),
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
  Widget build(BuildContext context) => Semantics(
    container: true,
    label: 'Ton cahier commence ici. Tes leçons et tes progrès apparaîtront ici après ta première révision.',
    child: ExcludeSemantics(
      child: Card(
        color: LudiColors.primary.withValues(alpha: 0.06),
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Container(
                width: 56,
                height: 56,
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(18),
                ),
                alignment: Alignment.center,
                child: const Text('📚', style: TextStyle(fontSize: 30)),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Ton cahier commence ici', style: Theme.of(context).textTheme.titleMedium),
                    const SizedBox(height: 4),
                    const Text(
                      'Tes leçons et tes progrès apparaîtront ici après ta première révision.',
                      style: TextStyle(fontSize: 14, height: 1.35),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    ),
  );
}

class _LessonRow extends ConsumerWidget {
  const _LessonRow(this.lesson);

  final LessonSummary lesson;

  Future<void> _open(BuildContext context, WidgetRef ref) async {
    switch (lesson.status) {
      case LessonStatus.ready when lesson.awaitingParent:
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Un adulte relit ta leçon avant que tu la révises. 🔒')),
        );
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
      // Relecture par l'adulte avant l'enfant (§5.69) : la leçon attend.
      LessonStatus.ready when lesson.awaitingParent => (
        lesson.title ?? 'Leçon',
        const Text('🔒 Un adulte la relit', style: TextStyle(fontSize: 15)),
        const Icon(Icons.lock_outline),
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
