import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/router.dart';
import '../../app/widgets.dart';
import '../../core/api/api_exception.dart';
import '../../core/session.dart';
import '../../models/parent.dart';
import 'lesson_image_card.dart';
import 'lesson_resources_card.dart';
import 'material_edit_sheet.dart';

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

/// Copie un texte dans le presse-papiers du téléphone, et le dit.
Future<void> copyText(BuildContext context, String text, String done) async {
  await Clipboard.setData(ClipboardData(text: text));
  if (context.mounted) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(done)));
  }
}

/// Les questions d'une notion, en texte simple (pour les copier ailleurs).
String notionText(NotionContent notion) => [
  notion.label,
  notion.statement,
  for (final block in notion.blocks) ...['', block.title, ...block.lines],
].join('\n');

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
      // Tout se sélectionne et se copie : la leçon lue par l'IA comme ses questions.
      body: SelectionArea(
        child: CenteredBody(
          top: true,
          children: switch (content) {
            AsyncData(:final value) => [
              Text(
                'Voici tout ce que l\'enfant verra (classe : ${value.grade}), réponses comprises. '
                'Si une réponse est fausse, corrigez-la vous-même ; si une question n\'est pas '
                'claire ou pas à son niveau, demandez une correction à l\'IA : sa progression '
                'n\'est pas touchée. Appuyez longuement sur un texte pour le copier.',
                style: const TextStyle(fontSize: 15, color: Colors.black54),
              ),
              if (value.notions.isNotEmpty)
                Align(
                  alignment: Alignment.centerLeft,
                  child: TextButton.icon(
                    onPressed: () => copyText(
                      context,
                      value.notions.map(notionText).join('\n\n'),
                      'Questions copiées.',
                    ),
                    icon: const Icon(Icons.copy_all_outlined),
                    label: const Text('Copier toutes les questions'),
                  ),
                ),
              const SizedBox(height: 12),
              LessonImageCard(childId: childId, lessonId: lessonId),
              LessonResourcesCard(childId: childId, lessonId: lessonId),
              if (value.text case final text?)
                Card(
                  margin: const EdgeInsets.only(bottom: 12),
                  child: ExpansionTile(
                    shape: const Border(),
                    leading: const Icon(Icons.menu_book_outlined),
                    title: const Text('La leçon, telle que l\'IA l\'a lue'),
                    subtitle: const Text(
                      'Vérifiez qu\'il ne manque rien et que rien n\'est mal lu',
                    ),
                    childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
                    expandedCrossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(text, style: const TextStyle(fontSize: 15, height: 1.4)),
                      TextButton.icon(
                        onPressed: () => copyText(context, text, 'Texte de la leçon copié.'),
                        icon: const Icon(Icons.copy_outlined),
                        label: const Text('Copier le texte'),
                      ),
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

  Future<void> _edit(BuildContext context, WidgetRef ref) async {
    final element = notion.editable.length == 1
        ? notion.editable.single
        : await pickEditable(context, notion);
    if (element == null || !context.mounted) return;
    final saved = await editMaterial(
      context,
      childId: childId,
      lessonId: lessonId,
      knowledgeId: notion.knowledgeId,
      element: element,
    );
    if (saved == null || !context.mounted) return;
    ref.invalidate(lessonContentProvider((childId, lessonId)));
    ScaffoldMessenger.of(context)
        .showSnackBar(const SnackBar(content: Text('Correction enregistrée.')));
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context).textTheme;
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: ExpansionTile(
        shape: const Border(),
        initiallyExpanded: notion.toCheck,
        title: Text('${notion.toCheck ? '⚠️ ' : ''}${notion.label}', style: theme.titleMedium),
        subtitle: Text(notion.statement),
        childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
        expandedCrossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (notion.toCheck) _ToCheck(notion, childId: childId, lessonId: lessonId),
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
          Wrap(
            spacing: 8,
            runSpacing: 4,
            children: [
              if (notion.editable.isNotEmpty)
                FilledButton.tonalIcon(
                  onPressed: () => _edit(context, ref),
                  icon: const Icon(Icons.edit_outlined),
                  label: const Text('Corriger moi-même'),
                ),
              OutlinedButton.icon(
                onPressed: () => _rework(context, ref),
                icon: const Icon(Icons.auto_fix_high),
                label: const Text('Demander une correction à l\'IA'),
              ),
              TextButton.icon(
                onPressed: () => copyText(context, notionText(notion), 'Questions copiées.'),
                icon: const Icon(Icons.copy_outlined),
                label: const Text('Copier'),
              ),
            ],
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

/// Notion lue avec peu de confiance (§115) : pourquoi, et la confirmer d'un geste.
class _ToCheck extends ConsumerWidget {
  const _ToCheck(this.notion, {required this.childId, required this.lessonId});

  final NotionContent notion;
  final String childId;
  final String lessonId;

  Future<void> _confirm(BuildContext context, WidgetRef ref) async {
    try {
      await ref.read(apiProvider).confirmNotion(childId, lessonId, notion.knowledgeId);
      ref.invalidate(lessonContentProvider((childId, lessonId)));
    } on ApiException catch (error) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(error.message)));
      }
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) => Container(
    margin: const EdgeInsets.only(top: 4, bottom: 8),
    padding: const EdgeInsets.all(12),
    decoration: BoxDecoration(
      color: Colors.orange.withValues(alpha: 0.1),
      borderRadius: BorderRadius.circular(12),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          notion.trust == 'low'
              ? 'Je ne suis pas sûr d\'avoir bien lu cette notion : elle n\'est pas proposée '
                    'tant que vous ne l\'avez pas vérifiée.'
              : 'Je ne suis pas tout à fait sûr d\'avoir bien lu cette notion : pouvez-vous '
                    'la comparer au cahier ?',
          style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
        ),
        for (final doubt in notion.doubts)
          Text('• $doubt', style: const TextStyle(fontSize: 14, color: Colors.black54)),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          runSpacing: 4,
          children: [
            FilledButton(
              onPressed: () => _confirm(context, ref),
              child: const Text('C\'est bien ce qui est écrit'),
            ),
          ],
        ),
        const Text(
          'Sinon : « Demander une correction à l\'IA » plus bas, ou reprendre la photo.',
          style: TextStyle(fontSize: 13, color: Colors.black54),
        ),
      ],
    ),
  );
}
