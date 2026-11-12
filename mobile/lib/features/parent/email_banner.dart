import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/theme.dart';
import '../../core/api/api_exception.dart';
import '../../core/session.dart';
import 'parent_home_screen.dart';
import 'parent_providers.dart';

/// « Confirmez votre adresse » tant que le parent n'a pas ouvert le lien de l'e-mail (étape 19).
/// Rien n'est bloqué : l'adresse sert au mot de passe oublié et aux messages importants.
class EmailVerificationBanner extends ConsumerStatefulWidget {
  const EmailVerificationBanner({super.key});

  @override
  ConsumerState<EmailVerificationBanner> createState() => _EmailVerificationBannerState();
}

class _EmailVerificationBannerState extends ConsumerState<EmailVerificationBanner> {
  bool _sending = false;

  Future<void> _resend() async {
    setState(() => _sending = true);
    try {
      await ref.read(apiProvider).resendEmailVerification();
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('Lien envoyé : regardez votre boîte e-mail.')));
      }
    } on ApiException catch (error) {
      if (!mounted) return;
      if (error.code == 'email_already_verified') {
        ref.invalidate(parentProfileProvider);
      } else {
        showError(context, error);
      }
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final profile = ref.watch(parentProfileProvider).value;
    if (profile == null || profile.emailVerified) return const SizedBox.shrink();
    return Card(
      color: LudiColors.accent.withValues(alpha: 0.12),
      margin: const EdgeInsets.only(bottom: 16),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('📧 Confirmez votre adresse', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 4),
            Text(
              'Ouvrez le lien envoyé à ${profile.email}. Elle sert si vous oubliez votre mot de '
              'passe, et pour les messages importants sur les données de vos enfants.',
            ),
            Wrap(
              alignment: WrapAlignment.end,
              children: [
                TextButton(
                  onPressed: () => ref.invalidate(parentProfileProvider),
                  child: const Text('C\'est fait'),
                ),
                TextButton(
                  onPressed: _sending ? null : _resend,
                  child: const Text('Renvoyer le lien'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
