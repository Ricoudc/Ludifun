import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/theme.dart';
import '../../app/widgets.dart';
import '../../core/api/api_exception.dart';
import '../../core/session.dart';
import '../../models/session.dart';

/// Aides déjà reçues, par activité : rouvrir la feuille les montre sans en redemander.
final helpMemoryProvider = Provider<Map<String, List<HelpStep>>>((ref) => {});

Future<void> showHelp(BuildContext context, String sessionId, String itemId) =>
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => HelpSheet(sessionId: sessionId, itemId: itemId),
    );

/// « ❓ Je n'ai pas compris » : indice, rappel, exemple, étapes, puis la réponse, une aide à la
/// fois et seulement si l'enfant en redemande (spécification technique §5.4).
class HelpSheet extends ConsumerStatefulWidget {
  const HelpSheet({required this.sessionId, required this.itemId, super.key});

  final String sessionId;
  final String itemId;

  @override
  ConsumerState<HelpSheet> createState() => _HelpSheetState();
}

class _HelpSheetState extends ConsumerState<HelpSheet> {
  late final List<HelpStep> _steps;
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _steps = ref.read(helpMemoryProvider).putIfAbsent(widget.itemId, () => []);
    if (_steps.isEmpty) _more();
  }

  Future<void> _more() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final step = await ref.read(apiProvider).help(widget.sessionId, widget.itemId);
      _steps.add(step);
    } on ApiException catch (error) {
      _error = error.message;
    }
    if (mounted) setState(() => _busy = false);
  }

  @override
  Widget build(BuildContext context) {
    final last = _steps.isNotEmpty && _steps.last.last;
    return SafeArea(
      child: ConstrainedBox(
        constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.8),
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(24, 0, 24, 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'Pas de souci, on regarde ensemble 🙂',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 16),
              for (final step in _steps) _StepCard(step),
              if (_busy) const Center(child: CircularProgressIndicator()),
              if (_error != null) ErrorMessage(_error!),
              const SizedBox(height: 8),
              if (!last && !_busy)
                OutlinedButton(
                  onPressed: _more,
                  child: Text(_steps.isEmpty ? 'Réessayer' : 'Encore de l\'aide'),
                ),
              const SizedBox(height: 8),
              FilledButton(
                onPressed: () => Navigator.of(context).pop(),
                child: const Text('J\'essaie !'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _StepCard extends StatelessWidget {
  const _StepCard(this.step);

  final HelpStep step;

  @override
  Widget build(BuildContext context) => Card(
    margin: const EdgeInsets.only(bottom: 12),
    color: LudiColors.primary.withValues(alpha: 0.06),
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(step.title, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
          const SizedBox(height: 6),
          Text(step.text, style: const TextStyle(fontSize: 19, height: 1.3)),
          for (final (i, line) in step.lines.indexed) ...[
            const SizedBox(height: 4),
            Text(
              step.kind == 'steps' ? '${i + 1}. $line' : line,
              style: const TextStyle(fontSize: 18, height: 1.3),
            ),
          ],
        ],
      ),
    ),
  );
}
