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
  owner: "bg-accent-purple/20 text-accent-purple",
  admin: "bg-primary/20 text-primary",
  manager: "bg-success/20 text-success",
  staff: "bg-warning/20 text-warning",
  accountant: "bg-warning/20 text-warning",
  viewer: "bg-secondary/20 text-secondary",
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
        <div className="w-12 h-12 rounded-xl bg-primary animate-pulse" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Team</h1>
          <p className="text-sm text-muted-foreground">
            Manage your team members and their permissions
          </p>
        </div>
        <button
          onClick={() => setShowInviteModal(true)}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-xl hover:bg-primary/90 transition-colors"
        >
          <UserPlus className="w-4 h-4" />
          Invite Member
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-card rounded-2xl p-6">
          <div className="flex items-center gap-3 mb-2">
            <Users className="w-5 h-5 text-primary" />
            <span className="text-sm text-muted-foreground">Total Members</span>
          </div>
          <p className="text-2xl font-bold text-foreground">{members.length}</p>
        </div>
        <div className="bg-card rounded-2xl p-6">
          <div className="flex items-center gap-3 mb-2">
            <Clock className="w-5 h-5 text-warning" />
            <span className="text-sm text-muted-foreground">Pending Invites</span>
          </div>
          <p className="text-2xl font-bold text-foreground">{invitations.length}</p>
        </div>
        <div className="bg-card rounded-2xl p-6">
          <div className="flex items-center gap-3 mb-2">
            <Shield className="w-5 h-5 text-success" />
            <span className="text-sm text-muted-foreground">Admins</span>
          </div>
          <p className="text-2xl font-bold text-foreground">
            {members.filter((m) => m.role === "admin" || m.role === "owner").length}
          </p>
        </div>
      </div>

      <div className="bg-card rounded-2xl overflow-hidden">
        <div className="p-4 border-b border-border">
          <h2 className="text-lg font-semibold text-foreground">Team Members</h2>
        </div>
        
        <div className="divide-y divide-border">
          {members.map((member) => (
            <div key={member.id} className="flex items-center justify-between p-4">
              <div className="flex items-center gap-4">
                <div className="w-10 h-10 rounded-full bg-muted flex items-center justify-center">
                  <span className="text-foreground font-medium">
                    {member.full_name.charAt(0).toUpperCase()}
                  </span>
                </div>
                <div>
                  <p className="font-medium text-foreground">{member.full_name}</p>
                  <p className="text-sm text-muted-foreground">{member.email}</p>
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
                    className="p-2 text-destructive hover:bg-destructive/10 rounded-lg transition-colors"
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
        <div className="bg-card rounded-2xl overflow-hidden">
          <div className="p-4 border-b border-border">
            <h2 className="text-lg font-semibold text-foreground">Pending Invitations</h2>
          </div>
          
          <div className="divide-y divide-border">
            {invitations.map((invite) => (
              <div key={invite.id} className="flex items-center justify-between p-4">
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 rounded-full bg-muted flex items-center justify-center">
                    <Mail className="w-5 h-5 text-muted-foreground" />
                  </div>
                  <div>
                    <p className="font-medium text-foreground">{invite.email}</p>
                    <p className="text-sm text-muted-foreground">
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
                    className="p-2 text-primary hover:bg-primary/10 rounded-lg transition-colors"
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
        <div className="fixed inset-0 bg-overlay flex items-center justify-center z-50">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="bg-card rounded-2xl p-6 w-full max-w-md"
          >
            <h3 className="text-lg font-semibold text-foreground mb-4">Invite Team Member</h3>
            
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-muted-foreground mb-2">Email</label>
                <input
                  type="email"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  className="w-full px-4 py-3 bg-muted rounded-xl text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                  placeholder="colleague@company.com"
                />
              </div>
              
              <div>
                <label className="block text-sm text-muted-foreground mb-2">Role</label>
                <select
                  value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value)}
                  className="w-full px-4 py-3 bg-muted rounded-xl text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
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
                  className="flex-1 px-4 py-3 bg-muted text-foreground rounded-xl hover:bg-muted transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleInvite}
                  disabled={!inviteEmail}
                  className="flex-1 px-4 py-3 bg-primary text-primary-foreground rounded-xl hover:bg-primary/90 transition-colors disabled:opacity-50"
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
