variable "groups" {
  description = "Okta groups to create."
  type = list(object({
    name        = string
    description = string
  }))
}

variable "group_rules" {
  description = "Okta group rules that dynamically assign users to a group based on a profile attribute expression, evaluated against every user in the org."
  type = list(object({
    name             = string
    group_name       = string
    expression_value = string
  }))
  default = []
}
