resource "okta_app_bookmark" "this" {
  for_each = { for a in var.apps : a.label => a }

  label  = each.value.label
  url    = each.value.url
  status = "ACTIVE"
}

resource "okta_app_group_assignment" "this" {
  for_each = { for a in var.assignments : "${a.app_label}::${a.group_name}" => a }

  app_id   = okta_app_bookmark.this[each.value.app_label].id
  group_id = var.group_ids[each.value.group_name]
}
