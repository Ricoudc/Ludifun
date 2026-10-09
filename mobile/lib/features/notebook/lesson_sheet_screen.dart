import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/api_image.dart';
import '../../app/level_stars.dart';
import '../../app/router.dart';
import '../../app/theme.dart';
import '../../app/widgets.dart';
import '../../core/api/api_exception.dart';
import '../../core/session.dart';
import '../../models/lesson_sheet.dart';
import '../../models/subject.dart';
import '../lesson/resource_tile.dart';
import '../session/activities/common.dart' show ListenButton;

final lessonSheetProvider = FutureProvider.autoDispose.family<LessonSheet, String>(
  (ref, lessonId) => ref.watch(apiProvider).lessonSheet(lessonId),
);

/// « Mon cahier » : la fiche de révision d'une leçon. On relit, on écoute, on regarde les
/// vidéos ; les jeux sont sur l'écran de la leçon.
class LessonSheetScreen extends ConsumerWidget {
  const LessonSheetScreen({required this.lessonId, super.key});

  final String lessonId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final sheet = ref.watch(lessonSheetProvider(lessonId));
    return Scaffold(
      appBar: AppBar(
        leading: BackButton(onPressed: () => context.go(Routes.notebook)),
        title: const Text('Ma fiche'),
      ),
      body: switch (sheet) {
        AsyncData(:final value) => _Sheet(value),
        AsyncError(:final error) => CenteredBody(
          children: [
            ErrorMessage(error is ApiException ? error.message : ApiException.unexpected),
            TextButton(
              onPressed: () => ref.invalidate(lessonSheetProvider(lessonId)),
              child: const Text('Réessayer'),
            ),
          ],
        ),
        _ => const Center(child: CircularProgressIndicator()),
      },
    );
  }
}

class _Sheet extends ConsumerWidget {
  const _Sheet(this.sheet);

  final LessonSheet sheet;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context).textTheme;
    return CenteredBody(
      top: true,
      children: [
        Text(
          '${Subjects.emoji(sheet.subject)} ${Subjects.label(sheet.subject).toUpperCase()}'
          '${sheet.grade == null ? '' : ' · ${sheet.grade}'}',
          style: theme.labelLarge?.copyWith(color: LudiColors.primary, letterSpacing: 1),
        ),
        const SizedBox(height: 6),
        Text(sheet.title ?? 'Ma leçon', style: theme.headlineMedium),
        if (sheet.image case final image?) ...[
          const SizedBox(height: 12),
          ClipRRect(
            borderRadius: BorderRadius.circular(16),
            child: SizedBox(
              height: 200,
              child: ApiImage(image.url, semanticLabel: image.alt, fit: BoxFit.contain),
            ),
          ),
        ],
        if (sheet.objective case final objective?) ...[
          const SizedBox(height: 12),
          Text('🎯 $objective', style: const TextStyle(fontSize: 17)),
        ],
        if (sheet.summary case final summary?) ...[
          const SizedBox(height: 12),
          _Paragraph('📝 En bref', summary),
        ],
        const SizedBox(height: 20),
        Text('À retenir', style: theme.titleLarge),
        const SizedBox(height: 8),
        for (final notion in sheet.notions) _NotionCard(notion),
        if (sheet.resources.isNotEmpty) ...[
          const SizedBox(height: 20),
          Text('🎬 Vidéos et exercices proposés', style: theme.titleLarge),
          const SizedBox(height: 4),
          for (final resource in sheet.resources)
            ResourceTile(
              lessonId: sheet.lessonId,
              resource: resource,
              onClosed: () => ref.invalidate(lessonSheetProvider(sheet.lessonId)),
            ),
        ],
        if (sheet.text case final text?) ...[
          const SizedBox(height: 12),
          ExpansionTile(
            tilePadding: EdgeInsets.zero,
            title: Text('📄 Ma leçon en entier', style: theme.titleMedium),
            children: [
              Align(
                alignment: Alignment.centerLeft,
                child: SelectableText(text, style: const TextStyle(fontSize: 16, height: 1.4)),
              ),
            ],
          ),
        ],
        const SizedBox(height: 20),
        OutlinedButton.icon(
          onPressed: () => context.go(Routes.lesson(sheet.lessonId)),
          icon: const Icon(Icons.sports_esports_outlined),
          label: const Text('M\'entraîner avec des jeux'),
        ),
      ],
    );
  }
}

class _Paragraph extends StatelessWidget {
  const _Paragraph(this.title, this.text);

  final String title;
  final String text;

  @override
  Widget build(BuildContext context) => Row(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Expanded(
        child: Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Text.rich(
            TextSpan(
              children: [
                TextSpan(
                  text: '$title : ',
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
                TextSpan(text: text),
              ],
            ),
            style: const TextStyle(fontSize: 17, height: 1.35),
          ),
        ),
      ),
      ListenButton([text]),
    ],
  );
}

class _NotionCard extends StatelessWidget {
  const _NotionCard(this.notion);

  final SheetNotion notion;

  @override
  Widget build(BuildContext context) => Card(
    margin: const EdgeInsets.only(bottom: 12),
    child: Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 8, 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(child: Text(notion.label, style: Theme.of(context).textTheme.titleMedium)),
              LevelStars(notion.level),
              ListenButton([notion.label, notion.statement, ?notion.explanation]),
            ],
          ),
          if (notion.image case final image?) ...[
            const SizedBox(height: 8),
            ClipRRect(
              borderRadius: BorderRadius.circular(12),
              child: SizedBox(
                height: 140,
                width: double.infinity,
                child: ApiImage(image, semanticLabel: notion.label, fit: BoxFit.contain),
              ),
            ),
          ],
          const SizedBox(height: 6),
          Text(
            notion.statement,
            style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600, height: 1.35),
          ),
          if (notion.explanation case final explanation? when explanation != notion.statement)
            _Line('💬', explanation),
          if (notion.tip case final tip?) _Line('💡 Astuce :', tip),
          if (notion.example case final example?)
            _Line(
              '✏️ Exemple :',
              '${example.question} → ${example.answer}'
                  '${example.why == null ? '' : ' (${example.why})'}',
            ),
          if ((notion.cardFront, notion.cardBack) case (final front?, final back?))
            _MemoryCard(front, back),
        ],
      ),
    ),
  );
}

class _Line extends StatelessWidget {
  const _Line(this.lead, this.text);

  final String lead;
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 8, right: 8),
    child: Text('$lead $text', style: const TextStyle(fontSize: 16, height: 1.35)),
  );
}

/// Carte mémoire : la question d'abord, la réponse quand on la retourne.
class _MemoryCard extends StatefulWidget {
  const _MemoryCard(this.front, this.back);

  final String front;
  final String back;

  @override
  State<_MemoryCard> createState() => _MemoryCardState();
}

class _MemoryCardState extends State<_MemoryCard> {
  bool _turned = false;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 10, right: 8),
    child: InkWell(
      borderRadius: BorderRadius.circular(12),
      onTap: () => setState(() => _turned = !_turned),
      child: Ink(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: LudiColors.accent.withValues(alpha: _turned ? 0.18 : 0.08),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Row(
          children: [
            Expanded(
              child: Text(
                _turned ? '✅ ${widget.back}' : '🃏 ${widget.front}',
                style: const TextStyle(fontSize: 16, height: 1.35),
              ),
            ),
            Text(
              _turned ? 'Cacher' : 'Retourner',
              style: const TextStyle(color: LudiColors.primary, fontWeight: FontWeight.w700),
            ),
          ],
        ),
      ),
    ),
  );
}
