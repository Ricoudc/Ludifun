import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/router.dart';
import '../../app/widgets.dart';
import '../../core/api/api_exception.dart';
import '../../core/session.dart';
import '../../models/parent.dart';
import 'parent_home_screen.dart';
import 'parent_providers.dart';

final familyMembersProvider = FutureProvider.autoDispose<FamilyMembers>(
  (ref) => ref.watch(apiProvider).familyMembers(),
);

/// « Second parent » (§5.92) : inviter l'autre parent, ou rejoindre sa famille avec son code.
/// Les deux parents voient les mêmes enfants, leçons et réglages.
class FamilyScreen extends ConsumerStatefulWidget {
  const FamilyScreen({super.key});

  @override
  ConsumerState<FamilyScreen> createState() => _FamilyScreenState();
}

class _FamilyScreenState extends ConsumerState<FamilyScreen> {
  final _code = TextEditingController();
  bool _busy = false;

  @override
  void dispose() {
    _code.dispose();
    super.dispose();
  }

  void _refresh() {
    ref
      ..invalidate(familyMembersProvider)
      ..invalidate(childrenProvider);
  }

  Future<void> _run(Future<void> Function() action) async {
    setState(() => _busy = true);
    try {
      await action();
    } on ApiException catch (error) {
      if (mounted) showError(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _invite() => _run(() async {
    final invite = await ref.read(apiProvider).inviteParent();
    if (!mounted) return;
    await showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Code pour l\'autre parent'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SelectableText(
              invite.code,
              style: const TextStyle(fontSize: 32, fontWeight: FontWeight.w800, letterSpacing: 2),
            ),
            const SizedBox(height: 8),
            const Text(
              'Donnez-lui ce code : dans Ludifun, sur son compte (sans enfant), Mon compte → Second '
              'parent → Rejoindre une famille. Valable 7 jours, une seule fois.',
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Clipboard.setData(ClipboardData(text: invite.code)),
            child: const Text('Copier'),
          ),
          TextButton(onPressed: () => Navigator.of(context).pop(), child: const Text('OK')),
        ],
      ),
    );
  });

  Future<void> _join() => _run(() async {
    await ref.read(apiProvider).joinFamily(_code.text.trim());
    _code.clear();
    _refresh();
    if (mounted) {
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('Vous avez rejoint la famille.')));
    }
  });

  Future<void> _remove(FamilyMemberInfo member, {required bool leaving}) async {
    final confirmed = await confirmDanger(
      context,
      title: leaving ? 'Quitter la famille ?' : 'Retirer ${member.email} ?',
      message: leaving
          ? 'Vous ne verrez plus les enfants de cette famille. Rien n\'est effacé pour eux.'
          : 'Ce parent ne verra plus les enfants. Rien n\'est effacé pour eux.',
      action: leaving ? 'Quitter' : 'Retirer',
    );
    if (!confirmed) return;
    await _run(() async {
      await ref.read(apiProvider).removeFamilyMember(member.parentId);
      _refresh();
    });
  }

  @override
  Widget build(BuildContext context) {
    final members = ref.watch(familyMembersProvider);
    return Scaffold(
      appBar: AppBar(
        leading: BackButton(onPressed: () => context.go(Routes.parentHome)),
        title: const Text('Second parent'),
      ),
      body: CenteredBody(
        top: true,
        children: switch (members) {
          AsyncData(:final value) => [
            const Text(
              'Les deux parents voient les mêmes enfants, leçons et réglages, chacun avec son '
              'propre compte.',
              style: TextStyle(fontSize: 15, color: Colors.black54),
            ),
            const SizedBox(height: 12),
            for (final m in value.members)
              Card(
                child: ListTile(
                  leading: Icon(m.owner ? Icons.home_outlined : Icons.person_add_alt),
                  title: Text(m.firstName ?? m.email),
                  subtitle: Text(
                    '${m.owner ? 'A créé la famille' : 'Second parent'}${m.me ? ' · vous' : ''}',
                  ),
                  trailing: switch ((value.me.owner, m.me, m.owner)) {
                    (true, false, false) => IconButton(
                      tooltip: 'Retirer ce parent',
                      icon: const Icon(Icons.person_remove_outlined),
                      onPressed: _busy ? null : () => _remove(m, leaving: false),
                    ),
                    (false, true, _) => TextButton(
                      onPressed: _busy ? null : () => _remove(m, leaving: true),
                      child: const Text('Quitter'),
                    ),
                    _ => null,
                  },
                ),
              ),
            if (value.canInvite) ...[
              const SizedBox(height: 8),
              FilledButton.icon(
                onPressed: _busy ? null : _invite,
                icon: const Icon(Icons.group_add_outlined),
                label: const Text('Inviter un second parent'),
              ),
            ],
            if (value.members.length == 1) ...[
              const SizedBox(height: 24),
              Text('Rejoindre une famille', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 4),
              const Text(
                'L\'autre parent vous a donné un code ? Votre compte ne doit pas avoir d\'enfant.',
                style: TextStyle(fontSize: 15),
              ),
              const SizedBox(height: 8),
              TextField(
                controller: _code,
                textCapitalization: TextCapitalization.characters,
                decoration: const InputDecoration(
                  labelText: 'Code d\'invitation',
                  hintText: 'Par exemple : ABCD-EFGH',
                ),
              ),
              const SizedBox(height: 8),
              OutlinedButton(onPressed: _busy ? null : _join, child: const Text('Rejoindre')),
            ],
          ],
          AsyncError() => [
            const Text('La famille n\'a pas pu être lue.', style: TextStyle(fontSize: 17)),
            const SizedBox(height: 12),
            FilledButton(onPressed: _refresh, child: const Text('Réessayer')),
          ],
          _ => [const Center(child: CircularProgressIndicator())],
        },
      ),
    );
  }
}
