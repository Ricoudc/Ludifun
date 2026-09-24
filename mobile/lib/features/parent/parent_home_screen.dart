import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/router.dart';
import '../../app/theme.dart';
import '../../app/widgets.dart';
import '../../core/api/api_exception.dart';
import '../../core/link_opener.dart';
import '../../core/session.dart';
import '../../core/storage/credentials.dart';
import '../../models/account.dart';
import 'email_banner.dart';
import 'feedback_dialog.dart';
import 'parent_providers.dart';

/// Écran P2 : les enfants de la famille.
class ParentHomeScreen extends ConsumerWidget {
  const ParentHomeScreen({super.key});

  Future<void> _deleteAccount(BuildContext context, WidgetRef ref) async {
    final confirmed = await confirmDanger(
      context,
      title: 'Supprimer votre compte ?',
      message:
          'Le compte, les profils de vos enfants, leurs leçons et leurs résultats seront '
          'définitivement effacés. Les tablettes liées seront déliées.',
      action: 'Supprimer définitivement',
    );
    if (!confirmed) return;
    try {
      await ref.read(apiProvider).deleteAccount();
      await ref.read(sessionProvider.notifier).forget();
    } on ApiException catch (error) {
      if (context.mounted) showError(context, error);
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final children = ref.watch(childrenProvider);
    final email = switch (ref.watch(sessionProvider).value) {
      ParentCredentials(:final email) => email,
      _ => '',
    };
    return Scaffold(
      appBar: AppBar(
        title: const Text('Mes enfants'),
        actions: [
          PopupMenuButton<String>(
            tooltip: 'Mon compte',
            icon: const Icon(Icons.account_circle_outlined),
            onSelected: (choice) => switch (choice) {
              'logout' => ref.read(sessionProvider.notifier).signOut(),
              'feedback' => showFeedbackDialog(context),
              'ai' => context.go(Routes.aiSettings),
              'privacy' => openPublicPage(ref, '/confidentialite'),
              _ => _deleteAccount(context, ref),
            },
            itemBuilder: (_) => [
              PopupMenuItem(enabled: false, child: Text(email)),
              const PopupMenuItem(value: 'ai', child: Text('Intelligence artificielle')),
              const PopupMenuItem(value: 'feedback', child: Text('Donner mon avis')),
              const PopupMenuItem(value: 'privacy', child: Text('Confidentialité')),
              const PopupMenuItem(value: 'logout', child: Text('Me déconnecter')),
              const PopupMenuItem(
                value: 'delete',
                child: Text(
                  'Supprimer mon compte',
                  style: TextStyle(color: LudiColors.notMastered),
                ),
              ),
            ],
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () {
          ref.invalidate(parentProfileProvider);
          return ref.refresh(childrenProvider.future);
        },
        child: CenteredBody(
          top: true,
          children: [
            const EmailVerificationBanner(),
            ...switch (children) {
              AsyncData(value: final list) when list.isEmpty => [
                const Text('👋', textAlign: TextAlign.center, style: TextStyle(fontSize: 48)),
                const SizedBox(height: 8),
                const Text(
                  'Ajoutez le profil de votre enfant, puis liez sa tablette ou son téléphone.',
                  textAlign: TextAlign.center,
                  style: TextStyle(fontSize: 18),
                ),
                const SizedBox(height: 24),
              ],
              AsyncData(value: final list) => [
                for (final child in list) ...[_ChildTile(child), const SizedBox(height: 12)],
                const SizedBox(height: 12),
              ],
              AsyncError(:final error) => [
                ErrorMessage(error is ApiException ? error.message : ApiException.unexpected),
                TextButton(
                  onPressed: () => ref.invalidate(childrenProvider),
                  child: const Text('Réessayer'),
                ),
              ],
              _ => [const Center(child: CircularProgressIndicator())],
            },
            FilledButton.icon(
              onPressed: () => context.go(Routes.addChild),
              icon: const Icon(Icons.add),
              label: const Text('Ajouter un enfant'),
            ),
          ],
        ),
      ),
    );
  }
}

class _ChildTile extends StatelessWidget {
  const _ChildTile(this.child);

  final Child child;

  @override
  Widget build(BuildContext context) => Card(
    child: ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      leading: CircleAvatar(
        radius: 24,
        backgroundColor: LudiColors.primary.withValues(alpha: 0.12),
        child: Text(avatarOf(child), style: const TextStyle(fontSize: 24)),
      ),
      title: Text(
        '${child.displayName} · ${child.grade}',
        style: Theme.of(context).textTheme.titleLarge,
      ),
      subtitle: child.devices == 0
          ? TextButton.icon(
              style: TextButton.styleFrom(
                padding: EdgeInsets.zero,
                alignment: Alignment.centerLeft,
              ),
              onPressed: () => context.go(Routes.childLink(child.id)),
              icon: const Icon(Icons.link),
              label: const Text('Lier un appareil'),
            )
          : Text(
              '📱 ${child.devices} appareil${child.devices > 1 ? 's' : ''} lié${child.devices > 1 ? 's' : ''}',
            ),
      trailing: const Icon(Icons.chevron_right),
      onTap: () => context.go(Routes.childDashboard(child.id)),
    ),
  );
}

/// Confirmation d'une action irréversible.
Future<bool> confirmDanger(
  BuildContext context, {
  required String title,
  required String message,
  required String action,
}) async =>
    await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(title),
        content: Text(message),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Annuler'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: LudiColors.notMastered,
              minimumSize: const Size(120, 48),
            ),
            onPressed: () => Navigator.of(context).pop(true),
            child: Text(action),
          ),
        ],
      ),
    ) ??
    false;

void showError(BuildContext context, ApiException error) =>
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(error.message)));
