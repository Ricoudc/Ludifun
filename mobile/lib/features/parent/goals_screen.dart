import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/format.dart' show longDate;
import '../../app/router.dart';
import '../../app/theme.dart';
import '../../app/widgets.dart';
import '../../core/api/api_exception.dart';
import '../../core/session.dart';
import '../../models/account.dart';
import '../../models/parent.dart';
import '../../models/subject.dart';
import 'parent_providers.dart';

const dailyMinutesChoices = [5, 10, 15, 20, 30];

/// Objectifs du parent (étape 16) : temps de révision par jour, matière à privilégier, et
/// contrôles à venir avec leur plan de révision, recalculé chaque jour.
class GoalsScreen extends ConsumerWidget {
  const GoalsScreen({required this.childId, super.key});

  final String childId;

  Future<void> _save(
    BuildContext context,
    WidgetRef ref,
    Child child, {
    int? minutes,
    String? subject,
    bool clearMinutes = false,
    bool clearSubject = false,
  }) async {
    try {
      await ref
          .read(apiProvider)
          .setGoals(
            child.id,
            dailyMinutes: clearMinutes ? null : minutes ?? child.dailyMinutes,
            prioritySubject: clearSubject ? null : subject ?? child.prioritySubject,
          );
      ref.invalidate(childrenProvider);
    } on ApiException catch (error) {
      if (context.mounted) showSnack(context, error.message);
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final child = ref.watch(childProvider(childId)).value;
    final exams = ref.watch(examsProvider(childId));
    final theme = Theme.of(context).textTheme;
    Widget section(String title) => Padding(
      padding: const EdgeInsets.only(top: 24, bottom: 8),
      child: Text(title, style: theme.titleLarge),
    );
    return Scaffold(
      appBar: AppBar(
        leading: BackButton(onPressed: () => context.go(Routes.childDashboard(childId))),
        title: Text(child == null ? 'Objectifs' : 'Objectifs · ${child.displayName}'),
      ),
      body: CenteredBody(
        top: true,
        children: [
          if (child == null)
            const Center(child: CircularProgressIndicator())
          else ...[
            Text('Temps de révision par jour', style: theme.titleLarge),
            const SizedBox(height: 4),
            const Text(
              'Les séances s\'adaptent à ce temps.',
              style: TextStyle(color: Colors.black54),
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                ChoiceChip(
                  label: const Text('Libre'),
                  selected: child.dailyMinutes == null,
                  onSelected: (_) => _save(context, ref, child, clearMinutes: true),
                ),
                for (final minutes in dailyMinutesChoices)
                  ChoiceChip(
                    label: Text('$minutes min'),
                    selected: child.dailyMinutes == minutes,
                    onSelected: (_) => _save(context, ref, child, minutes: minutes),
                  ),
              ],
            ),
            section('Matière à privilégier'),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                ChoiceChip(
                  label: const Text('Aucune'),
                  selected: child.prioritySubject == null,
                  onSelected: (_) => _save(context, ref, child, clearSubject: true),
                ),
                for (final subject in Subjects.all)
                  ChoiceChip(
                    label: Text('${Subjects.emoji(subject)} ${Subjects.label(subject)}'),
                    selected: child.prioritySubject == subject,
                    onSelected: (_) => _save(context, ref, child, subject: subject),
                  ),
              ],
            ),
          ],
          section('Contrôles à venir'),
          ...switch (exams) {
            AsyncData(value: []) => [
              const Text(
                'Ajoutez un contrôle : chaque jour jusqu\'à la veille, la mission du jour suit un plan de révision.',
                style: TextStyle(fontSize: 16),
              ),
            ],
            AsyncData(:final value) => [for (final exam in value) _ExamCard(childId, exam)],
            AsyncError(:final error) => [
              ErrorMessage(error is ApiException ? error.message : ApiException.unexpected),
            ],
            _ => [const Center(child: CircularProgressIndicator())],
          },
          const SizedBox(height: 12),
          OutlinedButton.icon(
            onPressed: () => showModalBottomSheet<void>(
              context: context,
              isScrollControlled: true,
              builder: (_) => ExamForm(childId: childId),
            ),
            icon: const Icon(Icons.event),
            label: const Text('Ajouter un contrôle'),
          ),
        ],
      ),
    );
  }
}

void showSnack(BuildContext context, String message) =>
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));

class _ExamCard extends ConsumerWidget {
  const _ExamCard(this.childId, this.exam);

  final String childId;
  final Exam exam;

  @override
  Widget build(BuildContext context, WidgetRef ref) => Card(
    margin: const EdgeInsets.only(bottom: 12),
    child: Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 8, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  '📅 ${exam.title} · ${longDate(exam.examDate)}',
                  style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700),
                ),
              ),
              IconButton(
                tooltip: 'Supprimer ce contrôle',
                icon: const Icon(Icons.delete_outline),
                onPressed: () async {
                  try {
                    await ref.read(apiProvider).deleteExam(childId, exam.id);
                    ref.invalidate(examsProvider(childId));
                  } on ApiException catch (error) {
                    if (context.mounted) showSnack(context, error.message);
                  }
                },
              ),
            ],
          ),
          if (exam.plan.isEmpty)
            const Text('C\'est le jour du contrôle : bonne chance !')
          else
            for (final step in exam.plan)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(
                  '${step.done ? '✅' : '▫️'} ${_capitalize(longDate(step.day))} : ${step.label}',
                  style: TextStyle(fontSize: 15, color: step.done ? LudiColors.mastered : null),
                ),
              ),
        ],
      ),
    ),
  );
}

String _capitalize(String text) => text.isEmpty ? text : text[0].toUpperCase() + text.substring(1);

/// Nouveau contrôle : un titre, une date (demain au plus tôt), les leçons à réviser.
class ExamForm extends ConsumerStatefulWidget {
  const ExamForm({required this.childId, super.key});

  final String childId;

  @override
  ConsumerState<ExamForm> createState() => _ExamFormState();
}

class _ExamFormState extends ConsumerState<ExamForm> {
  final _title = TextEditingController();
  final _lessons = <String>{};
  DateTime? _date;
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _title.dispose();
    super.dispose();
  }

  Future<void> _pickDate() async {
    final today = DateUtils.dateOnly(DateTime.now());
    final picked = await showDatePicker(
      context: context,
      initialDate: _date ?? today.add(const Duration(days: 3)),
      firstDate: today.add(const Duration(days: 1)),
      lastDate: today.add(const Duration(days: 60)),
      locale: const Locale('fr'),
    );
    if (picked != null) setState(() => _date = picked);
  }

  Future<void> _save() async {
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await ref
          .read(apiProvider)
          .createExam(
            widget.childId,
            title: _title.text.trim(),
            date: _date!,
            lessonIds: _lessons.toList(),
          );
      ref.invalidate(examsProvider(widget.childId));
      if (mounted) Navigator.of(context).pop();
    } on ApiException catch (error) {
      if (mounted) {
        setState(() {
          _saving = false;
          _error = error.message;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final lessons = ref.watch(childLessonsProvider(widget.childId));
    final ready = _title.text.trim().isNotEmpty && _date != null && _lessons.isNotEmpty && !_saving;
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.fromLTRB(24, 24, 24, 24 + MediaQuery.viewInsetsOf(context).bottom),
        child: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text('Nouveau contrôle', style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 12),
              TextField(
                controller: _title,
                maxLength: 80,
                decoration: const InputDecoration(labelText: 'Titre (ex. : contrôle de fractions)'),
                onChanged: (_) => setState(() {}),
              ),
              OutlinedButton.icon(
                onPressed: _pickDate,
                icon: const Icon(Icons.calendar_month),
                label: Text(_date == null ? 'Choisir la date' : longDate(_date!)),
              ),
              const SizedBox(height: 12),
              const Text('Leçons à réviser :', style: TextStyle(fontWeight: FontWeight.w600)),
              ...switch (lessons) {
                AsyncData(value: []) => [const Text('Aucune leçon prête pour l\'instant.')],
                AsyncData(:final value) => [
                  for (final lesson in value)
                    CheckboxListTile(
                      contentPadding: EdgeInsets.zero,
                      value: _lessons.contains(lesson.id),
                      title: Text('${Subjects.emoji(lesson.subject)} ${lesson.title ?? 'Leçon'}'),
                      onChanged: (checked) => setState(
                        () =>
                            checked == true ? _lessons.add(lesson.id) : _lessons.remove(lesson.id),
                      ),
                    ),
                ],
                AsyncError() => [const ErrorMessage(ApiException.unexpected)],
                _ => [const LinearProgressIndicator()],
              },
              if (_error != null) ErrorMessage(_error!),
              const SizedBox(height: 12),
              FilledButton(
                onPressed: ready ? _save : null,
                child: const Text('Enregistrer le contrôle'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
