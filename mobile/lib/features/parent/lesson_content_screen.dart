import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/router.dart';
import '../../app/widgets.dart';
import '../../core/api/api_exception.dart';
import '../../core/session.dart';
import '../../models/parent.dart';
import 'lesson_image_card.dart';

final lessonContentProvider = FutureProvider.autoDispose.family<LessonContent, (String, String)>(
  (ref, ids) => ref.watch(apiProvider).lessonContent(ids.$1, ids.$2),
);

/// Ce que le parent peut reprocher aux questions d'une notion (étape 25).
const reworkReasons = {
  'too_hard': 'Trop difficile',
  'too_easy': 'Trop facile',
  'unclear': 'Pas clair',
  'wrong': 'Réponse fausse',
  'other': 'Autre',
};

/// Toutes les questions d'une leçon, avec leurs réponses : le parent vérifie qu'elles sont
/// claires et à la classe de l'enfant, et peut en demander une nouvelle version à l'IA.
class LessonContentScreen extends ConsumerWidget {
  const LessonContentScreen({required this.childId, required this.lessonId, super.key});

  final String childId;
  final String lessonId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final content = ref.watch(lessonContentProvider((childId, lessonId)));
    return Scaffold(
      appBar: AppBar(
        leading: BackButton(onPressed: () => context.go(Routes.childDashboard(childId))),
        title: Text(content.value?.title ?? 'Questions de la leçon'),
      ),
      body: CenteredBody(
        top: true,
        children: switch (content) {
          AsyncData(:final value) => [
            Text(
              'Voici tout ce que l\'enfant verra (classe : ${value.grade}), réponses comprises. '
              'Si une question n\'est pas claire ou pas à son niveau, demandez une correction à '
              'l\'IA : sa progression n\'est pas touchée.',
              style: const TextStyle(fontSize: 15, color: Colors.black54),
            ),
            const SizedBox(height: 12),
            LessonImageCard(childId: childId, lessonId: lessonId),
            if (value.text case final text?)
              Card(
                margin: const EdgeInsets.only(bottom: 12),
                child: ExpansionTile(
                  shape: const Border(),
                  leading: const Icon(Icons.menu_book_outlined),
                  title: const Text('La leçon, telle que l\'IA l\'a lue'),
                  subtitle: const Text('Vérifiez qu\'il ne manque rien et que rien n\'est mal lu'),
                  childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
                  expandedCrossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SelectableText(text, style: const TextStyle(fontSize: 15, height: 1.4)),
                  ],
                ),
              ),
            for (final notion in value.notions)
              _NotionCard(notion, childId: childId, lessonId: lessonId),
          ],
          AsyncError(:final error) => [
            ErrorMessage(error is ApiException ? error.message : ApiException.unexpected),
            TextButton(
              onPressed: () => ref.invalidate(lessonContentProvider((childId, lessonId))),
              child: const Text('Réessayer'),
            ),
          ],
          _ => [const Center(child: CircularProgressIndicator())],
        },
      ),
    );
  }
}

class _NotionCard extends ConsumerWidget {
  const _NotionCard(this.notion, {required this.childId, required this.lessonId});

  final NotionContent notion;
  final String childId;
  final String lessonId;

  Future<void> _rework(BuildContext context, WidgetRef ref) async {
    final request = await showModalBottomSheet<(String, String?)>(
      context: context,
      isScrollControlled: true,
      builder: (_) => _ReworkSheet(label: notion.label),
    );
    if (request == null || !context.mounted) return;
    unawaited(
      showDialog<void>(
        context: context,
        barrierDismissible: false,
        builder: (_) => const AlertDialog(
          content: Row(
            children: [
              CircularProgressIndicator(),
              SizedBox(width: 20),
              Expanded(child: Text('L\'IA prépare de nouvelles questions… (une à deux minutes)')),
            ],
          ),
        ),
      ),
    );
    String? message;
    try {
      await ref
          .read(apiProvider)
          .reworkNotion(
            childId,
            lessonId,
            notion.knowledgeId,
            reason: request.$1,
            comment: request.$2,
          );
      message = 'Nouvelles questions enregistrées.';
    } on ApiException catch (error) {
      message = error.message;
    }
    if (!context.mounted) return;
    Navigator.of(context).pop();
    ref.invalidate(lessonContentProvider((childId, lessonId)));
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context).textTheme;
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: ExpansionTile(
        shape: const Border(),
        title: Text(notion.label, style: theme.titleMedium),
        subtitle: Text(notion.statement),
        childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
        expandedCrossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final block in notion.blocks) ...[
            const SizedBox(height: 8),
            Text(block.title, style: const TextStyle(fontWeight: FontWeight.w700)),
            if (block.instruction case final instruction?)
              Padding(
                padding: const EdgeInsets.only(top: 2, left: 8),
                child: Text(
                  'Consigne lue par l\'enfant : « $instruction »',
                  style: const TextStyle(
                    fontSize: 14,
                    fontStyle: FontStyle.italic,
                    color: Colors.black54,
                  ),
                ),
              ),
            for (final line in block.lines)
              Padding(
                padding: const EdgeInsets.only(top: 4, left: 8),
                child: Text(line, style: const TextStyle(fontSize: 15)),
              ),
          ],
          const SizedBox(height: 12),
          OutlinedButton.icon(
            onPressed: () => _rework(context, ref),
            icon: const Icon(Icons.auto_fix_high),
            label: const Text('Demander une correction à l\'IA'),
          ),
        ],
      ),
    );
  }
}

class _ReworkSheet extends StatefulWidget {
  const _ReworkSheet({required this.label});

  final String label;

  @override
  State<_ReworkSheet> createState() => _ReworkSheetState();
}

class _ReworkSheetState extends State<_ReworkSheet> {
  String? _reason;
  final _comment = TextEditingController();

  @override
  void dispose() {
    _comment.dispose();
    super.dispose();
  }

  bool get _ready => _reason != null && (_reason != 'other' || _comment.text.trim().isNotEmpty);

  @override
  Widget build(BuildContext context) => Padding(
    padding: EdgeInsets.fromLTRB(24, 24, 24, 24 + MediaQuery.viewInsetsOf(context).bottom),
    child: Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Qu\'est-ce qui ne va pas ?', style: Theme.of(context).textTheme.titleLarge),
        Text(widget.label, style: const TextStyle(color: Colors.black54)),
        const SizedBox(height: 12),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final MapEntry(:key, :value) in reworkReasons.entries)
              ChoiceChip(
                label: Text(value),
                selected: _reason == key,
                onSelected: (_) => setState(() => _reason = key),
              ),
          ],
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _comment,
          maxLength: 500,
          maxLines: 3,
          onChanged: (_) => setState(() {}),
          decoration: const InputDecoration(
            labelText: 'Précisez (facultatif)',
            hintText: 'Par exemple : « la question 2 utilise des mots trop compliqués »',
          ),
        ),
        const SizedBox(height: 8),
        FilledButton(
          onPressed: _ready
              ? () =>
                    Navigator.of(context)
                        .pop((_reason!, _comment.text.trim().isEmpty ? null : _comment.text.trim()))
              : null,
          child: const Text('Demander à l\'IA'),
        ),
      ],
    ),
  );
}
