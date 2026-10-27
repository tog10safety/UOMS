import { FormEvent, useEffect, useState } from 'react';

import { authApi } from '@/api/endpoints';
import { mrmApi } from '@/api/mrmApi';
import { AUTHORITY_LABEL } from '@/components/mrm/MrmBadges';
import { useAuth } from '@/contexts/AuthContext';
import { useToast } from '@/contexts/ToastContext';
import { extractApiError } from '@/utils/errors';

import { FormActions, TextField } from './FormFields';
import Modal from './Modal';

interface AccountModalProps {
  onClose: () => void;
  /** When true the user cannot dismiss the dialog until the password is changed. */
  forcePasswordChange?: boolean;
}

export default function AccountModal({ onClose, forcePasswordChange = false }: AccountModalProps) {
  const { user, refreshUser } = useAuth();
  const { showSuccess } = useToast();
  const [tab, setTab] = useState<'profile' | 'password' | 'signature'>(forcePasswordChange ? 'password' : 'profile');

  const [profile, setProfile] = useState({
    first_name: user?.first_name ?? '', last_name: user?.last_name ?? '',
    email: user?.email ?? '', phone_number: user?.phone_number ?? '',
  });
  const [passwords, setPasswords] = useState({ current: '', next: '', confirm: '' });
  const [error, setError] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  const [sigUrl, setSigUrl] = useState<string | null>(null);
  const [sigFile, setSigFile] = useState<File | null>(null);

  const loadSignature = async () => {
    if (!user?.has_signature) { setSigUrl(null); return; }
    try {
      const { blob } = await mrmApi.signatureImage();
      setSigUrl((old) => { if (old) URL.revokeObjectURL(old); return URL.createObjectURL(blob); });
    } catch { setSigUrl(null); }
  };
  useEffect(() => {
    if (tab === 'signature') void loadSignature();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, user?.has_signature]);

  const uploadSignature = async (e: FormEvent) => {
    e.preventDefault();
    if (!sigFile) return;
    setIsSaving(true);
    setError('');
    try {
      await mrmApi.uploadSignature(sigFile);
      await refreshUser();
      setSigFile(null);
      showSuccess('Signature saved.');
    } catch (err) {
      setError(extractApiError(err));
    } finally {
      setIsSaving(false);
    }
  };

  const removeSignature = async () => {
    try {
      await mrmApi.deleteSignature();
      await refreshUser();
      setSigUrl(null);
      showSuccess('Signature removed.');
    } catch (err) {
      setError(extractApiError(err));
    }
  };

  const saveProfile = async (e: FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    setError('');
    try {
      // Only the self-service fields are sent — role/unit/status are managed by administrators.
      await authApi.updateProfile(profile);
      await refreshUser();
      showSuccess('Profile updated.');
      onClose();
    } catch (err) {
      setError(extractApiError(err));
    } finally {
      setIsSaving(false);
    }
  };

  const savePassword = async (e: FormEvent) => {
    e.preventDefault();
    if (passwords.next !== passwords.confirm) {
      setError('The new password and its confirmation do not match.');
      return;
    }
    setIsSaving(true);
    setError('');
    try {
      await authApi.changePassword(passwords.current, passwords.next);
      await refreshUser();
      showSuccess('Password changed successfully.');
      onClose();
    } catch (err) {
      setError(extractApiError(err));
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Modal title={forcePasswordChange ? 'Password change required' : 'My Account'} onClose={forcePasswordChange ? undefined : onClose}>
      {forcePasswordChange ? (
        <p className="text-xs text-ops-warning">Your account requires a new password before you can continue.</p>
      ) : (
        <div className="flex gap-2">
          {(['profile', 'password', 'signature'] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => { setTab(t); setError(''); }}
              className={`rounded-md border px-3 py-1 text-xs font-medium ${
                tab === t ? 'border-ops-accent bg-ops-accent/10 text-ops-accent' : 'border-ops-border text-ops-textDim'
              }`}
            >
              {t === 'profile' ? 'Profile' : t === 'password' ? 'Change Password' : 'MRM Signature'}
            </button>
          ))}
        </div>
      )}

      {tab === 'profile' && !forcePasswordChange && (
        <form onSubmit={saveProfile} className="space-y-3">
          <p className="text-xs text-ops-textDim">
            Signed in as <span className="font-mono text-ops-text">{user?.username}</span> ({user?.role}
            {user?.unit_name ? ` — ${user.unit_name}` : ''}). Role, unit and MRM authority
            ({AUTHORITY_LABEL[user?.effective_mrm_authority ?? ''] ?? 'none'}{user?.mrm_designation ? `, ${user.mrm_designation.replace(/_/g, ' ').toLowerCase()}` : ''}) are managed by an administrator.
          </p>
          <div className="grid grid-cols-2 gap-3">
            <TextField label="First Name" value={profile.first_name} onChange={(v) => setProfile({ ...profile, first_name: v })} />
            <TextField label="Last Name" value={profile.last_name} onChange={(v) => setProfile({ ...profile, last_name: v })} />
            <TextField label="Email" type="email" required value={profile.email} onChange={(v) => setProfile({ ...profile, email: v })} />
            <TextField label="Phone Number" value={profile.phone_number} onChange={(v) => setProfile({ ...profile, phone_number: v })} />
          </div>
          {error && <p className="text-xs text-ops-danger">{error}</p>}
          <FormActions onCancel={onClose} isSaving={isSaving} />
        </form>
      )}

      {tab === 'signature' && !forcePasswordChange && (
        <form onSubmit={uploadSignature} className="space-y-3">
          <p className="text-xs text-ops-textDim">
            Your handwritten signature is printed on MRM forms you compile, review or approve. Use a PNG or JPEG (max 2 MB) on a white background.
            You must have one on file before you can approve an MRM.
          </p>
          <div className="flex h-24 items-center justify-center rounded-md border border-dashed border-ops-border bg-white">
            {sigUrl ? <img src={sigUrl} alt="Your signature" className="max-h-20" /> : <span className="text-xs text-gray-400">No signature on file</span>}
          </div>
          <input type="file" accept="image/png,image/jpeg" onChange={(e) => setSigFile(e.target.files?.[0] ?? null)}
                 className="block w-full text-xs text-ops-textDim file:mr-3 file:rounded-md file:border file:border-ops-border file:bg-ops-panelLight file:px-3 file:py-1.5 file:text-xs file:text-ops-text" />
          {error && <p className="text-xs text-ops-danger">{error}</p>}
          <div className="flex justify-between">
            {user?.has_signature ? <button type="button" onClick={removeSignature} className="text-xs text-ops-danger hover:underline">Remove signature</button> : <span />}
            <div className="flex gap-2">
              <button type="button" onClick={onClose} className="rounded-md border border-ops-border px-3 py-1.5 text-xs text-ops-textDim">Close</button>
              <button type="submit" disabled={!sigFile || isSaving} className="rounded-md bg-ops-accent px-3 py-1.5 text-xs font-semibold text-ops-bg disabled:opacity-50">{isSaving ? 'Uploading…' : 'Upload signature'}</button>
            </div>
          </div>
        </form>
      )}

      {tab === 'password' && (
        <form onSubmit={savePassword} className="space-y-3">
          <TextField label="Current Password" type="password" required value={passwords.current} onChange={(v) => setPasswords({ ...passwords, current: v })} />
          <TextField label="New Password" type="password" required value={passwords.next} onChange={(v) => setPasswords({ ...passwords, next: v })} />
          <TextField label="Confirm New Password" type="password" required value={passwords.confirm} onChange={(v) => setPasswords({ ...passwords, confirm: v })} />
          {error && <p className="text-xs text-ops-danger">{error}</p>}
          <FormActions onCancel={onClose} isSaving={isSaving} submitLabel="Change Password" />
        </form>
      )}
    </Modal>
  );
}
