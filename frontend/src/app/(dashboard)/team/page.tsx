"use client";

import { useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import { 
  Users, UserPlus, Mail, Shield, MoreVertical, 
  CheckCircle, Clock, XCircle, Copy, RefreshCw
} from "lucide-react";
import api from "@/lib/api";
import { useAppStore } from "@/stores/appStore";

interface TeamMember {
  id: string;
  user_id: string;
  email: string;
  full_name: string;
  role: string;
  permissions: string[];
  is_active: boolean;
  invited_at: string;
  accepted_at: string;
}

interface Invitation {
  id: string;
  email: string;
  role: string;
  status: string;
  expires_at: string;
  created_at: string;
}

const ROLE_COLORS: Record<string, string> = {
  owner: "bg-purple-500/20 text-purple-400",
  admin: "bg-blue-500/20 text-blue-400",
  manager: "bg-green-500/20 text-green-400",
  staff: "bg-yellow-500/20 text-yellow-400",
  accountant: "bg-orange-500/20 text-orange-400",
  viewer: "bg-gray-500/20 text-gray-400",
};

export default function TeamPage() {
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [loading, setLoading] = useState(true);
  const [showInviteModal, setShowInviteModal] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("staff");
  const { businessId } = useAppStore();

  const fetchTeam = useCallback(async () => {
    if (!businessId) return;
    try {
      const response = await api.get("/organizations/team", {
        params: { business_id: businessId },
      });
      setMembers(response.data);
      
      const invResponse = await api.get("/organizations/team/invitations", {
        params: { business_id: businessId },
      });
      setInvitations(invResponse.data || []);
    } catch (error) {
      console.error("Failed to fetch team:", error);
    } finally {
      setLoading(false);
    }
  }, [businessId]);

  useEffect(() => {
    fetchTeam();
  }, [fetchTeam]);

  const handleInvite = async () => {
    try {
      await api.post(
        "/organizations/team/invite",
        { email: inviteEmail, role: inviteRole },
        { params: { business_id: businessId } }
      );
      setShowInviteModal(false);
      setInviteEmail("");
      setInviteRole("staff");
      fetchTeam();
    } catch (error) {
      console.error("Failed to send invitation:", error);
    }
  };

  const handleRoleChange = async (memberId: string, newRole: string) => {
    try {
      await api.patch(
        `/organizations/team/${memberId}`,
        { role: newRole },
        { params: { business_id: businessId } }
      );
      fetchTeam();
    } catch (error) {
      console.error("Failed to update role:", error);
    }
  };

  const handleRemoveMember = async (memberId: string) => {
    if (!confirm("Are you sure you want to remove this team member?")) return;
    
    try {
      await api.delete(`/organizations/team/${memberId}`, {
        params: { business_id: businessId },
      });
      fetchTeam();
    } catch (error) {
      console.error("Failed to remove member:", error);
    }
  };

  const handleResendInvite = async (invitationId: string) => {
    try {
      await api.post(`/organizations/team/invitations/${invitationId}/resend`, {}, {
        params: { business_id: businessId },
      });
      fetchTeam();
    } catch (error) {
      console.error("Failed to resend invite:", error);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-12 h-12 rounded-xl bg-accent-blue animate-pulse" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-navy-text">Team</h1>
          <p className="text-sm text-navy-muted">
            Manage your team members and their permissions
          </p>
        </div>
        <button
          onClick={() => setShowInviteModal(true)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-500 text-white rounded-xl hover:bg-blue-600 transition-colors"
        >
          <UserPlus className="w-4 h-4" />
          Invite Member
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-navy-panel rounded-2xl p-6">
          <div className="flex items-center gap-3 mb-2">
            <Users className="w-5 h-5 text-blue-400" />
            <span className="text-sm text-navy-muted">Total Members</span>
          </div>
          <p className="text-2xl font-bold text-navy-text">{members.length}</p>
        </div>
        <div className="bg-navy-panel rounded-2xl p-6">
          <div className="flex items-center gap-3 mb-2">
            <Clock className="w-5 h-5 text-yellow-400" />
            <span className="text-sm text-navy-muted">Pending Invites</span>
          </div>
          <p className="text-2xl font-bold text-navy-text">{invitations.length}</p>
        </div>
        <div className="bg-navy-panel rounded-2xl p-6">
          <div className="flex items-center gap-3 mb-2">
            <Shield className="w-5 h-5 text-green-400" />
            <span className="text-sm text-navy-muted">Admins</span>
          </div>
          <p className="text-2xl font-bold text-navy-text">
            {members.filter((m) => m.role === "admin" || m.role === "owner").length}
          </p>
        </div>
      </div>

      <div className="bg-navy-panel rounded-2xl overflow-hidden">
        <div className="p-4 border-b border-navy-panel-2">
          <h2 className="text-lg font-semibold text-navy-text">Team Members</h2>
        </div>
        
        <div className="divide-y divide-navy-panel-2">
          {members.map((member) => (
            <div key={member.id} className="flex items-center justify-between p-4">
              <div className="flex items-center gap-4">
                <div className="w-10 h-10 rounded-full bg-navy-panel-2 flex items-center justify-center">
                  <span className="text-navy-text font-medium">
                    {member.full_name.charAt(0).toUpperCase()}
                  </span>
                </div>
                <div>
                  <p className="font-medium text-navy-text">{member.full_name}</p>
                  <p className="text-sm text-navy-muted">{member.email}</p>
                </div>
              </div>
              
              <div className="flex items-center gap-4">
                <select
                  value={member.role}
                  onChange={(e) => handleRoleChange(member.id, e.target.value)}
                  className={`px-3 py-1.5 rounded-lg text-sm ${ROLE_COLORS[member.role]}`}
                  disabled={member.role === "owner"}
                >
                  <option value="owner">Owner</option>
                  <option value="admin">Admin</option>
                  <option value="manager">Manager</option>
                  <option value="staff">Staff</option>
                  <option value="accountant">Accountant</option>
                  <option value="viewer">Viewer</option>
                </select>
                
                {member.role !== "owner" && (
                  <button
                    onClick={() => handleRemoveMember(member.id)}
                    className="p-2 text-red-400 hover:bg-red-500/10 rounded-lg transition-colors"
                    aria-label={`Remove ${member.full_name} from team`}
                  >
                    <XCircle className="w-4 h-4" />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {invitations.length > 0 && (
        <div className="bg-navy-panel rounded-2xl overflow-hidden">
          <div className="p-4 border-b border-navy-panel-2">
            <h2 className="text-lg font-semibold text-navy-text">Pending Invitations</h2>
          </div>
          
          <div className="divide-y divide-navy-panel-2">
            {invitations.map((invite) => (
              <div key={invite.id} className="flex items-center justify-between p-4">
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 rounded-full bg-navy-panel-2 flex items-center justify-center">
                    <Mail className="w-5 h-5 text-navy-muted" />
                  </div>
                  <div>
                    <p className="font-medium text-navy-text">{invite.email}</p>
                    <p className="text-sm text-navy-muted">
                      Invited as {invite.role} • Expires {new Date(invite.expires_at).toLocaleDateString()}
                    </p>
                  </div>
                </div>
                
                <div className="flex items-center gap-2">
                  <span className={`px-2 py-1 rounded text-xs ${ROLE_COLORS[invite.role]}`}>
                    {invite.role}
                  </span>
                  <button
                    onClick={() => handleResendInvite(invite.id)}
                    className="p-2 text-blue-400 hover:bg-blue-500/10 rounded-lg transition-colors"
                    aria-label={`Resend invitation to ${invite.email}`}
                  >
                    <RefreshCw className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {showInviteModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="bg-navy-panel rounded-2xl p-6 w-full max-w-md"
          >
            <h3 className="text-lg font-semibold text-navy-text mb-4">Invite Team Member</h3>
            
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-navy-muted mb-2">Email</label>
                <input
                  type="email"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  className="w-full px-4 py-3 bg-navy-panel-2 rounded-xl text-navy-text focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="colleague@company.com"
                />
              </div>
              
              <div>
                <label className="block text-sm text-navy-muted mb-2">Role</label>
                <select
                  value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value)}
                  className="w-full px-4 py-3 bg-navy-panel-2 rounded-xl text-navy-text focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="admin">Admin</option>
                  <option value="manager">Manager</option>
                  <option value="staff">Staff</option>
                  <option value="accountant">Accountant</option>
                  <option value="viewer">Viewer</option>
                </select>
              </div>
              
              <div className="flex gap-3 pt-4">
                <button
                  onClick={() => setShowInviteModal(false)}
                  className="flex-1 px-4 py-3 bg-navy-panel-2 text-navy-text rounded-xl hover:bg-navy-panel-3 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleInvite}
                  disabled={!inviteEmail}
                  className="flex-1 px-4 py-3 bg-blue-500 text-white rounded-xl hover:bg-blue-600 transition-colors disabled:opacity-50"
                >
                  Send Invite
                </button>
              </div>
            </div>
          </motion.div>
        </div>
      )}
    </div>
  );
}
