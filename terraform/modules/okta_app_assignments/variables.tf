variable "apps" {
  description = "Okta bookmark apps to create. Bookmark apps are used to keep this demo self-contained; a real org would more likely manage pre-existing SAML/OIDC apps, referenced via okta_app data sources, instead of creating them here."
  type = list(object({
    label = string
    url   = string
  }))
}

variable "assignments" {
  description = "Group-to-app assignments, referencing app labels from var.apps and group names from var.group_ids."
  type = list(object({
    app_label  = string
    group_name = string
  }))
}

variable "group_ids" {
  description = "Map of group name to group ID, as produced by the okta_groups module."
  type        = map(string)
}
