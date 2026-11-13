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
import 'lessons_panel.dart';
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
        actions: [
          IconButton(
            icon: const Icon(Icons.delete_outline),
            tooltip: 'Supprimer la leçon',
            onPressed: () async {
              final deleted = await deleteLessonAsParent(
                context,
                ref,
                childId: childId,
                lessonId: lessonId,
                title: content.value?.title,
              );
              if (deleted && context.mounted) context.go(Routes.childDashboard(childId));
            },
          ),
        ],
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
              if (value.notions.isNotEmpty) ...[
                const SizedBox(height: 8),
                OutlinedButton.icon(
                  onPressed: () => context.go(Routes.lessonTrial(childId, lessonId)),
                  icon: const Icon(Icons.play_circle_outline),
                  label: const Text('Essayer la leçon comme mon enfant'),
                ),
                const SizedBox(height: 4),
                OutlinedButton.icon(
                  onPressed: () => context.go(Routes.lessonTrial(childId, lessonId, full: true)),
                  icon: const Icon(Icons.playlist_play),
                  label: const Text('Essayer toute la leçon (chaque notion)'),
                ),
                const SizedBox(height: 4),
                _RecheckButton(childId: childId, lessonId: lessonId),
              ],
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
              _ReviewBanner(value, childId: childId, lessonId: lessonId),
              _LessonInfoCard(value, childId: childId, lessonId: lessonId),
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
              if (value.awaitingParent) ...[
                const SizedBox(height: 8),
                _ApproveButton(childId: childId, lessonId: lessonId),
              ],
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
        initiallyExpanded: notion.toCheck || notion.trialNotes.isNotEmpty,
        title: Text(
          '${notion.trialNotes.isNotEmpty ? '🚩 ' : ''}'
          '${notion.toCheck && !notion.removed ? '⚠️ ' : ''}${notion.label}'
          '${notion.removed ? ' (retirée)' : ''}',
          style: theme.titleMedium?.copyWith(
            decoration: notion.removed ? TextDecoration.lineThrough : null,
            color: notion.removed ? Colors.black45 : null,
          ),
        ),
        subtitle: Text(notion.statement),
        childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
        expandedCrossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (notion.toCheck) _ToCheck(notion, childId: childId, lessonId: lessonId),
          for (final note in notion.trialNotes)
            _TrialNoteTile(note, childId: childId, lessonId: lessonId),
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
              OutlinedButton.icon(
                onPressed: () => _editText(context, ref),
                icon: const Icon(Icons.short_text),
                label: const Text('Modifier le nom et la phrase'),
              ),
              if (notion.removed)
                OutlinedButton.icon(
                  onPressed: () => _setRemoved(context, ref, removed: false),
                  icon: const Icon(Icons.undo),
                  label: const Text('Remettre cette notion'),
                )
              else
                TextButton.icon(
                  onPressed: () => _setRemoved(context, ref, removed: true),
                  icon: const Icon(Icons.delete_outline),
                  label: const Text('Retirer cette notion'),
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

  Future<void> _editText(BuildContext context, WidgetRef ref) async {
    final values = await editTexts(
      context,
      title: 'Ce que l\'enfant doit retenir',
      fields: [
        ('Nom de la notion (pour une liste de mots : le mot à écrire)', notion.label, 120, 1),
        ('Phrase à retenir', notion.statement, 600, 4),
      ],
    );
    if (values == null || !context.mounted) return;
    await _save(
      context,
      ref,
      () => ref
          .read(apiProvider)
          .editNotionText(
            childId,
            lessonId,
            notion.knowledgeId,
            label: values[0],
            statement: values[1],
          ),
      'Notion corrigée.',
    );
  }

  Future<void> _setRemoved(BuildContext context, WidgetRef ref, {required bool removed}) async {
    if (removed) {
      final sure = await showDialog<bool>(
        context: context,
        builder: (dialog) => AlertDialog(
          title: const Text('Retirer cette notion ?'),
          content: Text(
            '« ${notion.label} » ne sera plus proposée à l\'enfant. Vous pourrez la remettre.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialog).pop(false),
              child: const Text('Annuler'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(dialog).pop(true),
              child: const Text('Retirer'),
            ),
          ],
        ),
      );
      if (sure != true || !context.mounted) return;
    }
    await _save(
      context,
      ref,
      () => ref
          .read(apiProvider)
          .setNotionRemoved(childId, lessonId, notion.knowledgeId, removed: removed),
      removed ? 'Notion retirée.' : 'Notion remise.',
    );
  }

  Future<void> _save(
    BuildContext context,
    WidgetRef ref,
    Future<Object?> Function() action,
    String done,
  ) async {
    String message = done;
    try {
      await action();
    } on ApiException catch (error) {
      message = error.message;
    }
    ref.invalidate(lessonContentProvider((childId, lessonId)));
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
    }
  }
}

/// Fenêtre à plusieurs champs de texte, pré-remplis ; `null` si le parent annule.
/// Chaque champ : (étiquette, valeur, longueur maximale, lignes).
Future<List<String>?> editTexts(
  BuildContext context, {
  required String title,
  required List<(String, String, int, int)> fields,
}) => showModalBottomSheet<List<String>>(
  context: context,
  isScrollControlled: true,
  builder: (_) => _TextsSheet(title: title, fields: fields),
);

class _TextsSheet extends StatefulWidget {
  const _TextsSheet({required this.title, required this.fields});

  final String title;
  final List<(String, String, int, int)> fields;

  @override
  State<_TextsSheet> createState() => _TextsSheetState();
}

class _TextsSheetState extends State<_TextsSheet> {
  late final _controllers = [for (final f in widget.fields) TextEditingController(text: f.$2)];

  @override
  void dispose() {
    for (final c in _controllers) {
      c.dispose();
    }
    super.dispose();
  }

  bool get _ready => _controllers.every((c) => c.text.trim().isNotEmpty);

  @override
  Widget build(BuildContext context) => Padding(
    padding: EdgeInsets.fromLTRB(24, 24, 24, 24 + MediaQuery.viewInsetsOf(context).bottom),
    child: SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(widget.title, style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 12),
          for (final (i, field) in widget.fields.indexed)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: TextField(
                controller: _controllers[i],
                maxLength: field.$3,
                minLines: 1,
                maxLines: field.$4,
                onChanged: (_) => setState(() {}),
                decoration: InputDecoration(labelText: field.$1),
              ),
            ),
          FilledButton(
            onPressed: _ready
                ? () => Navigator.of(context).pop([for (final c in _controllers) c.text.trim()])
                : null,
            child: const Text('Enregistrer'),
          ),
        ],
      ),
    ),
  );
}

/// Relecture avant l'enfant (§5.69) : ce que l'enfant attend, et « Valider la leçon ».
class _ReviewBanner extends StatelessWidget {
  const _ReviewBanner(this.content, {required this.childId, required this.lessonId});

  final LessonContent content;
  final String childId;
  final String lessonId;

  @override
  Widget build(BuildContext context) {
    if (!content.awaitingParent) {
      return content.approved
          ? const Padding(
              padding: EdgeInsets.only(bottom: 12),
              child: Text(
                '✅ Leçon validée : l\'enfant peut la réviser.',
                style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
              ),
            )
          : const SizedBox.shrink();
    }
    return Card(
      color: const Color(0xFFFFF3E0),
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text(
              '🔒 L\'enfant n\'a pas encore accès à cette leçon',
              style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 6),
            const Text(
              'L\'IA peut se tromper. Relisez le résumé, chaque notion et ses questions ; corrigez ou '
              'retirez ce qui est faux, puis validez.',
              style: TextStyle(fontSize: 15),
            ),
            const SizedBox(height: 12),
            _ApproveButton(childId: childId, lessonId: lessonId),
          ],
        ),
      ),
    );
  }
}

class _ApproveButton extends ConsumerWidget {
  const _ApproveButton({required this.childId, required this.lessonId});

  final String childId;
  final String lessonId;

  Future<void> _approve(BuildContext context, WidgetRef ref) async {
    String message = 'Leçon validée : l\'enfant peut la réviser.';
    try {
      await ref.read(apiProvider).approveLesson(childId, lessonId);
    } on ApiException catch (error) {
      message = error.message;
    }
    ref.invalidate(lessonContentProvider((childId, lessonId)));
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) => FilledButton.icon(
    onPressed: () => _approve(context, ref),
    icon: const Icon(Icons.check_circle_outline),
    label: const Text('Valider la leçon'),
  );
}

/// Titre, objectif et résumé que l'enfant lit ; le parent les corrige (§5.69).
class _LessonInfoCard extends ConsumerWidget {
  const _LessonInfoCard(this.content, {required this.childId, required this.lessonId});

  final LessonContent content;
  final String childId;
  final String lessonId;

  Future<void> _edit(BuildContext context, WidgetRef ref) async {
    final values = await editTexts(
      context,
      title: 'Titre et résumé de la leçon',
      fields: [
        ('Titre', content.title ?? '', 120, 1),
        ('Objectif', content.objective ?? '', 400, 3),
        ('Résumé', content.summary ?? '', 2000, 8),
      ],
    );
    if (values == null || !context.mounted) return;
    String message = 'Titre et résumé corrigés.';
    try {
      await ref
          .read(apiProvider)
          .editLessonInfo(
            childId,
            lessonId,
            title: values[0],
            objective: values[1],
            summary: values[2],
          );
    } on ApiException catch (error) {
      message = error.message;
    }
    ref.invalidate(lessonContentProvider((childId, lessonId)));
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (content.summary == null && content.objective == null) return const SizedBox.shrink();
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(content.title ?? 'Sans titre', style: Theme.of(context).textTheme.titleMedium),
            if (content.objective case final objective?) ...[
              const SizedBox(height: 4),
              Text('🎯 $objective', style: const TextStyle(fontSize: 15)),
            ],
            if (content.summary case final summary?) ...[
              const SizedBox(height: 4),
              Text(summary, style: const TextStyle(fontSize: 15, color: Colors.black87)),
            ],
            Align(
              alignment: Alignment.centerLeft,
              child: TextButton.icon(
                onPressed: () => _edit(context, ref),
                icon: const Icon(Icons.edit_outlined),
                label: const Text('Modifier le titre et le résumé'),
              ),
            ),
          ],
        ),
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

/// Une erreur notée pendant l'essai (§5.90) : à corriger ci-dessous, puis « C'est corrigé ».
class _TrialNoteTile extends ConsumerWidget {
  const _TrialNoteTile(this.note, {required this.childId, required this.lessonId});

  final TrialNote note;
  final String childId;
  final String lessonId;

  Future<void> _resolve(BuildContext context, WidgetRef ref) async {
    try {
      await ref.read(apiProvider).resolveTrialNote(childId, lessonId, note.id);
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
      color: Colors.red.withValues(alpha: 0.08),
      borderRadius: BorderRadius.circular(12),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          '🚩 Noté pendant l\'essai : il y a une erreur',
          style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: 4),
        Text('« ${note.question} »', style: const TextStyle(fontSize: 15)),
        if (note.answer case final answer?)
          Text(
            'Réponse donnée pour juste : $answer',
            style: const TextStyle(fontSize: 14, color: Colors.black54),
          ),
        const SizedBox(height: 4),
        const Text(
          'Corrigez la question ci-dessous (ou faites-la refaire par l\'IA), puis :',
          style: TextStyle(fontSize: 14, color: Colors.black54),
        ),
        TextButton.icon(
          onPressed: () => _resolve(context, ref),
          icon: const Icon(Icons.check),
          label: const Text('C\'est corrigé'),
        ),
      ],
    ),
  );
}

/// « Revérifier la leçon » (§5.91) : les contrôles d'aujourd'hui sur une leçon analysée avant.
class _RecheckButton extends ConsumerStatefulWidget {
  const _RecheckButton({required this.childId, required this.lessonId});

  final String childId;
  final String lessonId;

  @override
  ConsumerState<_RecheckButton> createState() => _RecheckButtonState();
}

class _RecheckButtonState extends ConsumerState<_RecheckButton> {
  bool _busy = false;

  Future<void> _recheck() async {
    setState(() => _busy = true);
    try {
      final result = await ref.read(apiProvider).recheckLesson(widget.childId, widget.lessonId);
      ref.invalidate(lessonContentProvider((widget.childId, widget.lessonId)));
      if (!mounted) return;
      final removed = result.findings.where((f) => !f.kept).toList();
      final kept = result.findings.where((f) => f.kept).toList();
      await showDialog<void>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('Leçon revérifiée'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (result.findings.isEmpty)
                  const Text('Tout passe les contrôles d\'aujourd\'hui : rien n\'a changé.'),
                if (removed.isNotEmpty) Text('${removed.length} élément(s) retiré(s) :'),
                for (final f in removed) Text('• ${f.label} : ${f.reason}'),
                if (kept.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  Text(
                    '${kept.length} question(s) gardée(s), car ce sont les dernières de leur '
                    'notion : à corriger vous-même.',
                  ),
                  for (final f in kept) Text('• ${f.label} : ${f.reason}'),
                ],
              ],
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.of(context).pop(), child: const Text('OK')),
          ],
        ),
      );
    } on ApiException catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(error.message)));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => OutlinedButton.icon(
    onPressed: _busy ? null : _recheck,
    icon: const Icon(Icons.fact_check_outlined),
    label: const Text('Revérifier la leçon (sans IA)'),
  );
}
