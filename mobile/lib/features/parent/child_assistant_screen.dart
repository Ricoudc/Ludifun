import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/router.dart';
import '../../app/widgets.dart';
import '../../core/api/api_exception.dart';
import '../../core/session.dart';
import '../../models/assistant.dart';

final assistantProvider = FutureProvider.autoDispose.family<List<AssistantAnswer>, String>(
  (ref, childId) => ref.watch(apiProvider).assistant(childId),
);

/// Assistant parent (§46) : le parent touche une question, la réponse vient des résultats réels
/// de l'enfant (pas d'IA : rien d'inventé) et dit sur quoi elle s'appuie.
class ChildAssistantScreen extends ConsumerStatefulWidget {
  const ChildAssistantScreen({required this.childId, super.key});

  final String childId;

  @override
  ConsumerState<ChildAssistantScreen> createState() => _ChildAssistantScreenState();
}

class _ChildAssistantScreenState extends ConsumerState<ChildAssistantScreen> {
  int _chosen = 0;

  @override
  Widget build(BuildContext context) {
    final answers = ref.watch(assistantProvider(widget.childId));
    return Scaffold(
      appBar: AppBar(
        leading: BackButton(onPressed: () => context.go(Routes.childDashboard(widget.childId))),
        title: const Text('Assistant'),
      ),
      body: switch (answers) {
        AsyncData(:final value) when value.isNotEmpty => _answers(context, value),
        AsyncError(:final error) => CenteredBody(
          children: [
            ErrorMessage(error is ApiException ? error.message : ApiException.unexpected),
            TextButton(
              onPressed: () => ref.invalidate(assistantProvider(widget.childId)),
              child: const Text('Réessayer'),
            ),
          ],
        ),
        _ => const Center(child: CircularProgressIndicator()),
      },
    );
  }

  Widget _answers(BuildContext context, List<AssistantAnswer> answers) {
    final answer = answers[_chosen.clamp(0, answers.length - 1)];
    return CenteredBody(
      top: true,
      children: [
        const Text(
          'Posez une question : la réponse est calculée à partir des résultats réels de '
          'l\'enfant, sans rien inventer.',
          style: TextStyle(fontSize: 15, color: Colors.black54),
        ),
        const SizedBox(height: 12),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final (i, a) in answers.indexed)
              ChoiceChip(
                label: Text(a.title),
                selected: i == _chosen,
                onSelected: (_) => setState(() => _chosen = i),
              ),
          ],
        ),
        const SizedBox(height: 16),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(answer.title, style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 8),
                for (final line in answer.lines)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 6),
                    child: Text(line, style: const TextStyle(fontSize: 16, height: 1.35)),
                  ),
                if (answer.basedOn.isNotEmpty) ...[
                  const Divider(height: 20),
                  Text(
                    'D\'après : ${answer.basedOn.join(' · ')}',
                    style: const TextStyle(fontSize: 13, color: Colors.black54),
                  ),
                ],
              ],
            ),
          ),
        ),
      ],
    );
  }
}
