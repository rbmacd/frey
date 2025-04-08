# frey
Frey - NetDevOps in a Box

Frey is a NetDevOps Distribution designed to streamline NetDevOps tooling installation and configuration, allowing network engineers to take advantage of DevOps concepts quickly and easily.

Getting started with NetDevOps can be overwhelming, given the plethora of bespoke tools and technologies available.  Many engineers find themselves struggling to get started because the process of identifying the tools required, configuration and integration of said tools requires deep knowledge of each tool, solid understanding of operating systems and virtualization concepts, container and container orchestration concepts, pipelines, network simulations, linting, and more.  Frey helps ease this barrier to entry.

Frey is highly opinionated in its tool selection.  The project maintainers select the tools included in the distribution based on the following criteria:
 - Open source and freely available (wherever possible)
 - Popularity within the community
 - Ease of use

The Frey Project's goal is to integrate popular DevOps tools together in a seamless manner for ease of implementation and day to day usage.  Frey does NOT focus on creating new NetDevOps tools.  

## Network Automation Phases and Technology Selections

Many different paradigms exist for codifying the stages of the NetDevOps lifecycle and there is no "correct" answer.  The Frey Project breaks down NetDevOps in to the following stages:
 - Source(s) of Truth
 - Automation & Orchestration
 - The Network
 - Simulation & Verification
 - Pipeline(s)
 - Observability / Assurance

Appropriate tools must be selected for each of these stages, based on the criteria listed above.  Care must be taken in not selecting too many tools for each stage, as the complexity of integrating the various tools together grows as the number of possible combinations increases.

The following table identifies technologies that the Frey project has targeted for its distribution.

| Source(s) of Truth | Automation & Orchestration | The Network | Simulation & Verification | Pipeline | Observability / Assurance | 
| ------------------ | -------------------------- | ------------------- | ---------- | --------- | ------------------------------ | 
| NetBox<br/>Nautobot | Ansible<br/>Python | Cisco<br/>Arista<br/>Juniper | netlab<br/>pybatfish<br/>pyATS<br/>ANTA<br/>pytest | gitlab<br/>github actions | icinga<br/>prometheus<br/>grafana | 
