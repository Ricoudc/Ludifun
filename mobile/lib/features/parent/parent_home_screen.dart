import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/router.dart';
import '../../app/theme.dart';
import '../../app/widgets.dart';
import '../../core/api/api_exception.dart';
import '../../core/app_update.dart';
import '../../core/link_opener.dart';
import '../../core/session.dart';
import '../../core/storage/credentials.dart';
import '../../models/account.dart';
import 'email_banner.dart';
import 'feedback_dialog.dart';
import 'parent_providers.dart';
import 'installation_screen.dart';
import 'reminders_card.dart';

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
              'installation' => context.go(Routes.installation),
              'family' => context.go(Routes.family),
              'privacy' => openPublicPage(ref, '/confidentialite'),
              _ => _deleteAccount(context, ref),
            },
            itemBuilder: (_) => [
              PopupMenuItem(enabled: false, child: Text(email)),
              const PopupMenuItem(value: 'ai', child: Text('Intelligence artificielle')),
              const PopupMenuItem(value: 'installation', child: Text('État de l\'installation')),
              const PopupMenuItem(value: 'family', child: Text('Second parent')),
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
          ref.invalidate(remindersProvider);
          ref.invalidate(installationProvider);
          return ref.refresh(childrenProvider.future);
        },
        child: CenteredBody(
          top: true,
          children: [
            Card(
              clipBehavior: Clip.antiAlias,
              color: LudiColors.primary,
              child: Padding(
                padding: const EdgeInsets.fromLTRB(18, 18, 18, 20),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                    Container(
                      width: 52,
                      height: 52,
                      decoration: BoxDecoration(
                        color: Colors.white.withValues(alpha: 0.16),
                        borderRadius: BorderRadius.circular(17),
                      ),
                      child: const Icon(
                        Icons.family_restroom_rounded,
                        color: Colors.white,
                        size: 29,
                      ),
                    ),
                    const SizedBox(width: 14),
                    const Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Chaque progrès compte.',
                            style: TextStyle(
                              color: Colors.white,
                              fontSize: 20,
                              fontWeight: FontWeight.w800,
                              height: 1.2,
                            ),
                          ),
                          SizedBox(height: 6),
                          Text(
                            'Suivez les apprentissages et accompagnez chaque étape.',
                            style: TextStyle(color: Colors.white, height: 1.35),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 8),
            const _ParentSectionLabel(
              icon: Icons.people_alt_outlined,
              title: 'Les profils de la famille',
              subtitle: 'Retrouvez le suivi de chaque enfant.',
            ),
            const AppUpdateBanner(),
            const EmailVerificationBanner(),
            const InstallationCard(),
            const RemindersCard(),
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

class _ParentSectionLabel extends StatelessWidget {
  const _ParentSectionLabel({required this.icon, required this.title, required this.subtitle});

  final IconData icon;
  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.fromLTRB(4, 8, 4, 12),
    child: Row(
      children: [
        Icon(icon, color: LudiColors.primary, size: 22),
        const SizedBox(width: 10),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 2),
              Text(subtitle, style: Theme.of(context).textTheme.bodySmall),
            ],
          ),
        ),
      ],
    ),
  );
}

class _ChildTile extends StatelessWidget {
  const _ChildTile(this.child);

  final Child child;

  @override
  Widget build(BuildContext context) {
    final linked = child.devices > 0;
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () => context.go(Routes.childDashboard(child.id)),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(14, 14, 10, 14),
          child: Row(
            children: [
              Container(
                width: 54,
                height: 54,
                decoration: BoxDecoration(
                  color: LudiColors.primary.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(17),
                ),
                alignment: Alignment.center,
                child: Text(avatarOf(child), style: const TextStyle(fontSize: 30)),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '${child.displayName} · ${child.grade}',
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                    const SizedBox(height: 5),
                    Row(
                      children: [
                        Icon(
                          linked ? Icons.devices_rounded : Icons.link_off_rounded,
                          size: 16,
                          color: linked ? LudiColors.mastered : LudiColors.toReview,
                        ),
                        const SizedBox(width: 5),
                        Expanded(
                          child: Text(
                            linked
                                ? '${child.devices} appareil${child.devices > 1 ? 's' : ''} lié${child.devices > 1 ? 's' : ''}'
                                : 'Aucun appareil lié',
                            style: TextStyle(
                              fontSize: 13,
                              color: linked ? LudiColors.mastered : LudiColors.toReview,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                      ],
                    ),
                    if (!linked)
                      Align(
                        alignment: Alignment.centerLeft,
                        child: TextButton.icon(
                          style: TextButton.styleFrom(
                            padding: const EdgeInsets.only(top: 5),
                            minimumSize: const Size(0, 32),
                            tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                          ),
                          onPressed: () => context.go(Routes.childLink(child.id)),
                          icon: const Icon(Icons.add_link, size: 17),
                          label: const Text('Lier un appareil'),
                        ),
                      ),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right, color: LudiColors.primary),
            ],
          ),
        ),
      ),
    );
  }
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
