import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/router.dart';
import '../../app/widgets.dart';
import '../../core/api/api_exception.dart';
import '../../core/session.dart';

/// Écran P1 : connexion ou création du compte parent.
class ParentSignInScreen extends ConsumerStatefulWidget {
  const ParentSignInScreen({this.register = false, super.key});

  final bool register;

  @override
  ConsumerState<ParentSignInScreen> createState() => _ParentSignInScreenState();
}

class _ParentSignInScreenState extends ConsumerState<ParentSignInScreen> {
  static const minPassword = 12;
  final _form = GlobalKey<FormState>();
  final _email = TextEditingController();
  final _password = TextEditingController();
  bool _acceptedPolicy = false;
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_form.currentState!.validate()) return;
    if (widget.register && !_acceptedPolicy) {
      setState(() => _error = 'Acceptez la politique de confidentialité pour créer votre compte.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    final api = ref.read(apiProvider);
    try {
      final email = _email.text.trim();
      final tokens = widget.register
          ? await api.register(email: email, password: _password.text)
          : await api.login(email: email, password: _password.text);
      await ref.read(sessionProvider.notifier).signedIn(tokens); // le routeur ouvre l'espace parent
    } on ApiException catch (error) {
      if (mounted) {
        setState(() {
          _busy = false;
          _error = error.message;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final register = widget.register;
    return Scaffold(
      appBar: AppBar(
        leading: BackButton(onPressed: () => context.go(Routes.start)),
        title: Text(register ? 'Créer mon compte parent' : 'Espace parent'),
      ),
      body: Form(
        key: _form,
        child: CenteredBody(
          children: [
            TextFormField(
              controller: _email,
              decoration: const InputDecoration(labelText: 'Adresse e-mail'),
              keyboardType: TextInputType.emailAddress,
              autofillHints: const [AutofillHints.email],
              textInputAction: TextInputAction.next,
              validator: (v) =>
                  v != null && v.contains('@') ? null : 'Saisissez une adresse e-mail valide.',
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _password,
              decoration: InputDecoration(
                labelText: 'Mot de passe',
                helperText: register ? 'Au moins $minPassword caractères.' : null,
              ),
              obscureText: true,
              autofillHints: [register ? AutofillHints.newPassword : AutofillHints.password],
              onFieldSubmitted: (_) => _submit(),
              validator: (v) => switch (v) {
                null || '' => 'Saisissez votre mot de passe.',
                final p when register && p.length < minPassword =>
                  'Au moins $minPassword caractères.',
                _ => null,
              },
            ),
            if (register) ...[
              const SizedBox(height: 8),
              CheckboxListTile(
                value: _acceptedPolicy,
                onChanged: (v) => setState(() => _acceptedPolicy = v ?? false),
                contentPadding: EdgeInsets.zero,
                controlAffinity: ListTileControlAffinity.leading,
                title: const Text(
                  'J\'accepte la politique de confidentialité : les photos des leçons ne sont '
                  'jamais conservées, aucune publicité.',
                ),
              ),
            ],
            if (_error != null) ...[const SizedBox(height: 16), ErrorMessage(_error!)],
            const SizedBox(height: 24),
            FilledButton(
              onPressed: _busy ? null : _submit,
              child: _busy
                  ? const SizedBox.square(dimension: 24, child: CircularProgressIndicator())
                  : Text(register ? 'Créer mon compte' : 'Me connecter'),
            ),
            const SizedBox(height: 12),
            TextButton(
              onPressed: () => context.go(register ? Routes.parentSignIn : Routes.parentRegister),
              child: Text(register ? 'J\'ai déjà un compte' : 'Créer un compte parent'),
            ),
          ],
        ),
      ),
    );
  }
}
