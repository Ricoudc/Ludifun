import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/router.dart';
import '../../core/session.dart';
import '../../models/reminder.dart';
import '../home/home_providers.dart';

final remindersProvider = FutureProvider.autoDispose<List<ParentReminder>>(
  (ref) => ref.watch(apiProvider).reminders(),
);

/// Jour où le parent a masqué les rappels (jusqu'au lendemain).
final remindersHiddenProvider = NotifierProvider<RemindersHidden, DateTime?>(RemindersHidden.new);

class RemindersHidden extends Notifier<DateTime?> {
  @override
  DateTime? build() => null;

  void hide(DateTime now) => state = DateTime(now.year, now.month, now.day);
}

/// Rappels du jour en haut de l'accueil du parent : discrets, et masquables pour la journée.
class RemindersCard extends ConsumerWidget {
  const RemindersCard({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final now = ref.watch(nowProvider)();
    final hidden = ref.watch(remindersHiddenProvider);
    final today = DateTime(now.year, now.month, now.day);
    final reminders = ref.watch(remindersProvider).value ?? const [];
    if (reminders.isEmpty || hidden == today) return const SizedBox.shrink();
    return Card(
      margin: const EdgeInsets.only(bottom: 16),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 8, 4),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Aujourd\'hui', style: Theme.of(context).textTheme.titleMedium),
            for (final reminder in reminders)
              InkWell(
                onTap: () => context.go(Routes.childDashboard(reminder.childId)),
                child: Padding(
                  padding: const EdgeInsets.only(top: 8, right: 8),
                  child: Text(reminder.text, style: const TextStyle(fontSize: 15, height: 1.35)),
                ),
              ),
            Align(
              alignment: Alignment.centerRight,
              child: TextButton(
                onPressed: () => ref.read(remindersHiddenProvider.notifier).hide(now),
                child: const Text('Masquer pour aujourd\'hui'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
