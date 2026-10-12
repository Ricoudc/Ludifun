import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/format.dart';
import '../../app/router.dart';
import '../../app/theme.dart';
import '../../app/widgets.dart';
import '../../core/api/api_exception.dart';
import '../../core/session.dart';
import '../../models/parent.dart';
import '../../models/subject.dart';
import '../home/home_providers.dart';
import 'child_mistakes_screen.dart' show ofName;
import 'lesson_content_screen.dart' show lessonContentProvider;
import 'material_edit_sheet.dart';
import 'parent_providers.dart';

/// Les questions que l'enfant a signalées (🚩) : la raison choisie, sa réponse, celle retenue par
/// Ludifun. Le parent ouvre les questions de la leçon pour corriger, puis marque comme vu.
class ChildReportsScreen extends ConsumerStatefulWidget {
  const ChildReportsScreen({required this.childId, super.key});

  final String childId;

  @override
  ConsumerState<ChildReportsScreen> createState() => _ChildReportsScreenState();
}

class _ChildReportsScreenState extends ConsumerState<ChildReportsScreen> {
  final _reports = <QuestionReport>[];
  String? _nextBefore;
  bool _loading = true;
  bool _complete = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadMore();
  }

  Future<void> _loadMore() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final page = await ref
          .read(apiProvider)
          .questionReports(widget.childId, before: _reports.isEmpty ? null : _nextBefore);
      _reports.addAll(page.reports);
      _nextBefore = page.nextBefore;
      _complete = page.nextBefore == null;
    } on ApiException catch (error) {
      _error = error.message;
    }
    if (mounted) setState(() => _loading = false);
  }

  Future<void> _markSeen(QuestionReport report) async {
    try {
      await ref.read(apiProvider).markReportSeen(widget.childId, report.id);
    } on ApiException catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(error.message)));
      }
      return;
    }
    if (!mounted) return;
    setState(() {
      final index = _reports.indexWhere((r) => r.id == report.id);
      if (index >= 0) _reports[index] = report.markedSeen();
    });
    ref.invalidate(dashboardProvider(widget.childId));
  }

  /// « Corriger la réponse » : la question est retrouvée dans les questions de la leçon, le
  /// parent la corrige, et le signalement est marqué comme vu (§5.59).
  Future<void> _correct(QuestionReport report, EditTarget target) async {
    final api = ref.read(apiProvider);
    EditableElement? element;
    try {
      final content = await api.lessonContent(widget.childId, report.lessonId);
      final notion = content.notions.where((n) => n.knowledgeId == target.knowledgeId).firstOrNull;
      element = notion?.editable
          .where((e) => e.kind == target.kind && e.index == target.index)
          .firstOrNull;
    } on ApiException catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(error.message)));
      }
      return;
    }
    if (!mounted) return;
    if (element == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'Cette question a changé depuis : ouvrez les questions de la leçon pour la corriger.',
          ),
        ),
      );
      return;
    }
    final saved = await editMaterial(
      context,
      childId: widget.childId,
      lessonId: report.lessonId,
      knowledgeId: target.knowledgeId,
      element: element,
    );
    if (saved == null || !mounted) return;
    ref.invalidate(lessonContentProvider((widget.childId, report.lessonId)));
    ScaffoldMessenger.of(context)
        .showSnackBar(const SnackBar(content: Text('Correction enregistrée.')));
    if (!report.seen) await _markSeen(report);
  }

  @override
  Widget build(BuildContext context) {
    final name = ref.watch(childProvider(widget.childId)).value?.displayName ?? '';
    final now = ref.watch(nowProvider)();
    return Scaffold(
      appBar: AppBar(
        leading: BackButton(onPressed: () => context.go(Routes.childDashboard(widget.childId))),
        title: Text(name.isEmpty ? 'Questions signalées' : 'Questions signalées ${ofName(name)}'),
      ),
      body: SelectionArea(
        child: CenteredBody(
          top: true,
          children: [
            const Text(
              'L\'enfant touche « 🚩 Signaler un problème » après une correction. Si la réponse '
              'retenue est fausse, corrigez-la vous-même ; sinon ouvrez les questions de la leçon. '
              'Le signalement ne change ni la note ni la progression.',
              style: TextStyle(fontSize: 15, color: Colors.black54),
            ),
            const SizedBox(height: 12),
            if (_reports.isEmpty && !_loading && _error == null)
              Text(
                name.isEmpty ? 'Aucune question signalée.' : '$name n\'a signalé aucune question.',
                style: const TextStyle(fontSize: 17),
              ),
            for (final report in _reports)
              _ReportCard(
                report,
                now,
                onOpenLesson: () =>
                    context.go(Routes.lessonContent(widget.childId, report.lessonId)),
                onSeen: () => _markSeen(report),
                onCorrect: report.edit == null ? null : () => _correct(report, report.edit!),
              ),
            if (_error != null) ErrorMessage(_error!),
            if (_loading)
              const Padding(
                padding: EdgeInsets.all(12),
                child: Center(child: CircularProgressIndicator()),
              )
            else if (!_complete || _error != null)
              TextButton(
                onPressed: _loadMore,
                child: const Text('Voir les signalements plus anciens'),
              ),
          ],
        ),
      ),
    );
  }
}

class _ReportCard extends StatelessWidget {
  const _ReportCard(
    this.report,
    this.now, {
    required this.onOpenLesson,
    required this.onSeen,
    this.onCorrect,
  });

  final QuestionReport report;
  final DateTime now;
  final VoidCallback onOpenLesson;
  final VoidCallback onSeen;

  /// Absent : question calculée par le code, ou serveur plus ancien.
  final VoidCallback? onCorrect;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context).textTheme;
    final verdict = switch (report.outcome) {
      HelpOutcome.right => 'Ludifun l\'a compté juste.',
      HelpOutcome.partial => 'Ludifun l\'a compté en partie juste.',
      HelpOutcome.wrong => 'Ludifun l\'a compté faux.',
      HelpOutcome.unanswered => 'Signalée avant de répondre.',
    };
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              report.reasonLabel,
              style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
            ),
            Text(
              '🚩 ${whenAt(report.reportedAt, now)} · ${Subjects.emoji(report.subject)} '
              '${report.lessonTitle ?? 'Leçon'}',
              style: const TextStyle(color: Colors.black54),
            ),
            if (report.question.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text(report.question, style: theme.titleMedium),
            ],
            const SizedBox(height: 8),
            if (report.given case final given?)
              Text('Sa réponse : $given', style: const TextStyle(fontSize: 15)),
            if (report.expected case final expected?)
              Text(
                'Réponse retenue : $expected',
                style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
              ),
            Text(verdict, style: const TextStyle(fontSize: 14, color: Colors.black54)),
            if (report.notions.isNotEmpty)
              Text(
                'Notion : ${report.notions.join(', ')}',
                style: const TextStyle(fontSize: 13, color: Colors.black54),
              ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 4,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                if (onCorrect case final onCorrect?)
                  FilledButton.tonalIcon(
                    onPressed: onCorrect,
                    icon: const Icon(Icons.edit_outlined),
                    label: const Text('Corriger la réponse'),
                  ),
                OutlinedButton(onPressed: onOpenLesson, child: const Text('Questions de la leçon')),
                if (report.seen)
                  const Padding(
                    padding: EdgeInsets.symmetric(horizontal: 8),
                    child: Text(
                      '✓ Vu',
                      style: TextStyle(color: LudiColors.mastered, fontWeight: FontWeight.w700),
                    ),
                  )
                else
                  TextButton(onPressed: onSeen, child: const Text('Marquer comme vu')),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
