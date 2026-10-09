import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/api_image.dart';
import '../../app/format.dart';
import '../../app/level_stars.dart';
import '../../app/router.dart';
import '../../app/theme.dart';
import '../../app/widgets.dart';
import '../../core/api/api_exception.dart';
import '../../core/offline.dart';
import '../../core/session.dart';
import '../../models/lesson.dart';
import '../../models/session.dart';
import '../../models/subject.dart';
import '../home/home_providers.dart';
import 'resource_tile.dart';

final lessonProvider = FutureProvider.autoDispose.family<Lesson, String>(
  (ref, id) => ref.watch(apiProvider).lesson(id),
);

/// La séance est créée dès l'ouverture de l'écran : la durée affichée est la vraie.
/// `null` : tout est à jour pour cette leçon.
final lessonSessionProvider = FutureProvider.autoDispose.family<RevisionSession?, String>((
  ref,
  lessonId,
) async {
  // Une séance gardée pour jouer sans Internet est reprise : en commencer une autre l'abandonnerait.
  final offline = ref.read(offlineSessionsProvider);
  if (await offline.forLesson(lessonId) case final pack?) {
    try {
      final kept = await ref.watch(apiProvider).session(pack.sessionId);
      if (kept.status == 'active') return kept;
      await offline.forget(pack.sessionId); // terminée ailleurs
    } on ApiException catch (error) {
      if (isOfflineError(error)) return pack.session;
      rethrow;
    }
  }
  try {
    return await ref.watch(apiProvider).startSession(lessonId);
  } on ApiException catch (error) {
    if (error.code == 'nothing_to_review') return null;
    rethrow;
  }
});

/// Écran 4 : résumé de la leçon et notions à retenir.
class LessonScreen extends ConsumerWidget {
  const LessonScreen({required this.lessonId, super.key});

  final String lessonId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final lesson = ref.watch(lessonProvider(lessonId));
    return Scaffold(
      appBar: AppBar(leading: BackButton(onPressed: () => context.go(Routes.childHome))),
      body: switch (lesson) {
        AsyncData(:final value) => _Summary(value),
        AsyncError(:final error) => CenteredBody(
          children: [
            ErrorMessage(error is ApiException ? error.message : ApiException.unexpected),
            TextButton(
              onPressed: () => ref.invalidate(lessonProvider(lessonId)),
              child: const Text('Réessayer'),
            ),
          ],
        ),
        _ => const Center(child: CircularProgressIndicator()),
      },
    );
  }
}

class _Summary extends ConsumerWidget {
  const _Summary(this.lesson);

  final Lesson lesson;

  Future<void> _changeGrade(BuildContext context, WidgetRef ref) async {
    final grade = await showModalBottomSheet<String>(
      context: context,
      builder: (context) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text('Tu es en quelle classe ?', style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 16),
              Wrap(
                spacing: 10,
                runSpacing: 10,
                alignment: WrapAlignment.center,
                children: [
                  for (final g in grades)
                    ChoiceChip(
                      label: Text(g, style: const TextStyle(fontSize: 18)),
                      selected: g == lesson.grade,
                      onSelected: (_) => Navigator.of(context).pop(g),
                    ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
    if (grade == null || grade == lesson.grade) return;
    try {
      await ref.read(apiProvider).setGrade(lesson.id, grade);
      ref.invalidate(lessonProvider(lesson.id));
    } on ApiException catch (error) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(error.message)));
      }
    }
  }

  void _showStatement(BuildContext context, Knowledge knowledge) => showModalBottomSheet<void>(
    context: context,
    isScrollControlled: knowledge.image != null,
    builder: (context) => SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(knowledge.label, style: Theme.of(context).textTheme.titleLarge),
            if (knowledge.image case final image?) ...[
              const SizedBox(height: 12),
              ClipRRect(
                borderRadius: BorderRadius.circular(16),
                child: SizedBox(
                  height: 180,
                  width: double.infinity,
                  child: ApiImage(image, semanticLabel: knowledge.label, fit: BoxFit.contain),
                ),
              ),
            ],
            const SizedBox(height: 12),
            Text(knowledge.statement, style: const TextStyle(fontSize: 18)),
            if (knowledge.sourceExcerpt case final excerpt?) ...[
              const SizedBox(height: 20),
              Text(
                knowledge.sourcePage == null
                    ? 'Pourquoi cette notion ? C\'est écrit dans ta leçon :'
                    : 'Pourquoi cette notion ? C\'est écrit dans ta leçon, page ${knowledge.sourcePage} :',
                style: Theme.of(context).textTheme.labelLarge,
              ),
              const SizedBox(height: 6),
              Text(
                '« $excerpt »',
                style: const TextStyle(
                  fontSize: 16,
                  fontStyle: FontStyle.italic,
                  color: Colors.black54,
                ),
              ),
            ],
          ],
        ),
      ),
    ),
  );

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(lessonSessionProvider(lesson.id));
    final theme = Theme.of(context).textTheme;
    final revision = session.value;
    return CenteredBody(
      top: true,
      children: [
        Text(
          '${Subjects.emoji(lesson.subject)} ${Subjects.label(lesson.subject).toUpperCase()}'
          '${lesson.grade == null ? '' : ' · ${lesson.grade}'}',
          style: theme.labelLarge?.copyWith(color: LudiColors.primary, letterSpacing: 1),
        ),
        const SizedBox(height: 6),
        Text(lesson.title ?? 'Ta leçon', style: theme.headlineMedium),
        const SizedBox(height: 16),
        if (lesson.image case final image?) _LessonPicture(image),
        if (revision?.objective ?? lesson.objective case final objective?)
          Text('🎯 Objectif : $objective', style: const TextStyle(fontSize: 17)),
        const SizedBox(height: 6),
        switch (session) {
          AsyncData(value: final s?) => Text(
            '⏱️ Durée estimée : ${s.estimatedMinutes} min${s.express ? ' · ⚡ révision express' : ''}',
            style: const TextStyle(fontSize: 17),
          ),
          AsyncLoading() => const Text('⏱️ …', style: TextStyle(fontSize: 17)),
          _ => const SizedBox(),
        },
        if (lesson.skills.isNotEmpty) ...[
          const SizedBox(height: 24),
          Text('Tu vas savoir :', style: theme.titleLarge),
          const SizedBox(height: 8),
          for (final skill in lesson.skills)
            ListTile(
              contentPadding: EdgeInsets.zero,
              dense: true,
              leading: const Icon(Icons.flag_outlined, color: LudiColors.primary),
              title: Text(skill.label, style: const TextStyle(fontSize: 18)),
              trailing: LevelStars(skill.level),
            ),
        ],
        const SizedBox(height: 24),
        Text('À retenir :', style: theme.titleLarge),
        const SizedBox(height: 8),
        for (final knowledge in lesson.knowledge)
          ListTile(
            contentPadding: EdgeInsets.zero,
            dense: true,
            leading: switch (knowledge.image) {
              // Image de la notion validée par le parent (étape 28) : on apprend aussi en la voyant.
              final image? => ClipRRect(
                borderRadius: BorderRadius.circular(8),
                child: SizedBox.square(dimension: 44, child: ApiImage(image)),
              ),
              // Même largeur qu'une image : les noms des notions restent alignés.
              null => const SizedBox.square(
                dimension: 44,
                child: Icon(Icons.lightbulb_outline, color: LudiColors.accent),
              ),
            },
            title: Text(knowledge.label, style: const TextStyle(fontSize: 18)),
            trailing: LevelStars(knowledge.level),
            onTap: () => _showStatement(context, knowledge),
          ),
        if (lesson.resources.isNotEmpty) ...[
          const SizedBox(height: 24),
          Text('🌐 Pour s\'entraîner autrement :', style: theme.titleLarge),
          const SizedBox(height: 4),
          for (final resource in lesson.resources)
            ResourceTile(
              lessonId: lesson.id,
              resource: resource,
              onClosed: () => ref.invalidate(lessonProvider(lesson.id)), // meilleur score à jour
            ),
        ],
        const SizedBox(height: 24),
        ...switch (session) {
          AsyncData(value: final s?) => [
            FilledButton(
              style: FilledButton.styleFrom(backgroundColor: LudiColors.accent),
              onPressed: () => context.go(Routes.session(s.id)),
              child: const Text('Commencer la révision'),
            ),
            const SizedBox(height: 8),
            _KeepOffline(sessionId: s.id, lessonTitle: lesson.title),
          ],
          AsyncData(value: null) => [
            Text(
              '🎉 Tout est à jour pour cette leçon !'
              '${lesson.nextReviewAt == null ? '' : ' Reviens ${dayLabel(lesson.nextReviewAt!, ref.watch(nowProvider)())}.'}',
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 18),
            ),
          ],
          AsyncError(:final error) => [
            ErrorMessage(error is ApiException ? error.message : ApiException.unexpected),
            TextButton(
              onPressed: () => ref.invalidate(lessonSessionProvider(lesson.id)),
              child: const Text('Réessayer'),
            ),
          ],
          _ => [const Center(child: CircularProgressIndicator())],
        },
        const SizedBox(height: 8),
        OutlinedButton.icon(
          onPressed: () => context.go(Routes.lessonSheet(lesson.id)),
          icon: const Icon(Icons.menu_book_outlined),
          label: const Text('Relire ma fiche (sans jeux)'),
        ),
        const SizedBox(height: 8),
        _TeachMe(lesson.id),
        TextButton(
          onPressed: () => _changeGrade(context, ref),
          child: const Text('Ce n\'est pas le bon niveau ?'),
        ),
      ],
    );
  }
}

/// Image validée par le parent ; absente ou illisible, la leçon s'affiche sans elle.
class _LessonPicture extends ConsumerWidget {
  const _LessonPicture(this.image);

  final LessonIllustration image;

  @override
  Widget build(BuildContext context, WidgetRef ref) =>
      switch (ref.watch(imageBytesProvider(image.url))) {
        AsyncData(:final value) => Padding(
          padding: const EdgeInsets.only(bottom: 16),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(16),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 280),
              child: Image.memory(
                value,
                semanticLabel: image.alt,
                fit: BoxFit.contain,
                errorBuilder: (_, _, _) => const SizedBox(),
              ),
            ),
          ),
        ),
        _ => const SizedBox(),
      };
}

/// « Garder pour jouer sans Internet » : la séance reste sur le téléphone ; les réponses
/// seront corrigées au retour du réseau.
class _KeepOffline extends ConsumerStatefulWidget {
  const _KeepOffline({required this.sessionId, this.lessonTitle});

  final String sessionId;
  final String? lessonTitle;

  @override
  ConsumerState<_KeepOffline> createState() => _KeepOfflineState();
}

class _KeepOfflineState extends ConsumerState<_KeepOffline> {
  bool _busy = false;

  Future<void> _keep() async {
    setState(() => _busy = true);
    String message;
    try {
      await ref
          .read(offlineSessionsProvider)
          .download(widget.sessionId, lessonTitle: widget.lessonTitle);
      message = 'Séance gardée : tu pourras la jouer sans Internet, depuis l\'accueil.';
    } on ApiException catch (error) {
      message = error.message;
    }
    if (!mounted) return;
    setState(() => _busy = false);
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    final kept =
        ref.watch(offlinePacksProvider).value?.any((p) => p.sessionId == widget.sessionId) ?? false;
    return TextButton.icon(
      onPressed: kept || _busy ? null : _keep,
      icon: Icon(kept ? Icons.offline_pin : Icons.download_for_offline_outlined),
      label: Text(kept ? 'Gardée pour jouer sans Internet' : 'Garder pour jouer sans Internet'),
    );
  }
}

/// « Enseigne-moi » (§83) : l'enfant explique à Ludi une notion choisie par le moteur.
class _TeachMe extends ConsumerStatefulWidget {
  const _TeachMe(this.lessonId);

  final String lessonId;

  @override
  ConsumerState<_TeachMe> createState() => _TeachMeState();
}

class _TeachMeState extends ConsumerState<_TeachMe> {
  bool _starting = false;

  Future<void> _start() async {
    setState(() => _starting = true);
    try {
      final teach = await ref.read(apiProvider).startTeaching(widget.lessonId);
      if (mounted) context.go(Routes.teach(teach.id));
      return;
    } on ApiException catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(error.message)));
      }
    }
    if (mounted) setState(() => _starting = false);
  }

  @override
  Widget build(BuildContext context) => OutlinedButton.icon(
    onPressed: _starting ? null : _start,
    icon: const Icon(Icons.record_voice_over_outlined),
    label: const Text('Enseigne-moi : explique ta leçon à Ludi'),
  );
}
