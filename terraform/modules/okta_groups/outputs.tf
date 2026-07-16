output "group_ids" {
  description = "Map of group name to Okta group ID, for use by other modules (app assignments, policies)."
  value       = { for name, group in okta_group.this : name => group.id }
}

output "group_rule_ids" {
  description = "Map of group rule name to Okta group rule ID."
  value       = { for name, rule in okta_group_rule.this : name => rule.id }
}
