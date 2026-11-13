# 🏗️ JARVIS_Xerife: Mapa de Arquitetura Dinâmico
> **Protocolo de Simbiose:** Documentação gerada via análise de código real.

```mermaid
graph LR
    classDef core fill:#1a1f25,stroke:#00ff00,color:#fff,stroke-width:2px;
    classDef adapter fill:#1a1f25,stroke:#007bff,color:#fff;
    classDef port fill:#1a1f25,stroke:#ffa500,color:#fff,stroke-dasharray: 5 5;
    classDef support fill:#2d333b,stroke:#6c757d,color:#aaa;
    mobile["<b>mobile</b>"]
    class mobile support
    mobile_android["<b>android</b>"]
    class mobile_android support
    mobile --> mobile_android
    mobile_android_app["<b>app</b>"]
    class mobile_android_app support
    mobile_android --> mobile_android_app
    mobile_android_app_src["<b>src</b>"]
    class mobile_android_app_src support
    mobile_android_app --> mobile_android_app_src
    mobile_android_app_src_test["<b>test</b>"]
    class mobile_android_app_src_test support
    mobile_android_app_src --> mobile_android_app_src_test
    mobile_android_app_src_test_java["<b>java</b>"]
    class mobile_android_app_src_test_java support
    mobile_android_app_src_test --> mobile_android_app_src_test_java
    mobile_android_app_src_test_java_com["<b>com</b>"]
    class mobile_android_app_src_test_java_com support
    mobile_android_app_src_test_java --> mobile_android_app_src_test_java_com
    mobile_android_app_src_test_java_com_thedrack["<b>thedrack</b>"]
    class mobile_android_app_src_test_java_com_thedrack support
    mobile_android_app_src_test_java_com --> mobile_android_app_src_test_java_com_thedrack
    mobile_android_app_src_test_java_com_thedrack_jarvismobile["<b>jarvismobile</b>"]
    class mobile_android_app_src_test_java_com_thedrack_jarvismobile support
    mobile_android_app_src_test_java_com_thedrack --> mobile_android_app_src_test_java_com_thedrack_jarvismobile
    mobile_android_app_src_main["<b>main</b>"]
    class mobile_android_app_src_main support
    mobile_android_app_src --> mobile_android_app_src_main
    mobile_android_app_src_main_res["<b>res</b>"]
    class mobile_android_app_src_main_res support
    mobile_android_app_src_main --> mobile_android_app_src_main_res
    mobile_android_app_src_main_res_xml["<b>xml</b>"]
    class mobile_android_app_src_main_res_xml support
    mobile_android_app_src_main_res --> mobile_android_app_src_main_res_xml
    mobile_android_app_src_main_java["<b>java</b>"]
    class mobile_android_app_src_main_java support
    mobile_android_app_src_main --> mobile_android_app_src_main_java
    mobile_android_app_src_main_java_com["<b>com</b>"]
    class mobile_android_app_src_main_java_com support
    mobile_android_app_src_main_java --> mobile_android_app_src_main_java_com
    mobile_android_app_src_main_java_com_thedrack["<b>thedrack</b>"]
    class mobile_android_app_src_main_java_com_thedrack support
    mobile_android_app_src_main_java_com --> mobile_android_app_src_main_java_com_thedrack
    mobile_android_app_src_main_java_com_thedrack_jarvismobile["<b>jarvismobile</b>"]
    class mobile_android_app_src_main_java_com_thedrack_jarvismobile support
    mobile_android_app_src_main_java_com_thedrack --> mobile_android_app_src_main_java_com_thedrack_jarvismobile
    requirements["<b>requirements</b>"]
    class requirements support
    data["<b>data</b>"]
    class data support
    data_jrvs["<b>jrvs</b>"]
    class data_jrvs support
    data --> data_jrvs
    data_curiosity["<b>curiosity</b>"]
    class data_curiosity support
    data --> data_curiosity
    data_portas["<b>portas</b>"]
    class data_portas support
    data --> data_portas
    data_portas_macros["<b>macros</b>"]
    class data_portas_macros support
    data_portas --> data_portas_macros
    desktop["<b>desktop</b>"]
    class desktop support
    linux["<b>linux</b>"]
    class linux support
    linux_systemd["<b>systemd</b>"]
    class linux_systemd support
    linux --> linux_systemd
    static["<b>static</b>"]
    class static support
    _backups["<b>.backups</b>"]
    class _backups support
    _backups_cleanup["<b>cleanup</b>"]
    class _backups_cleanup support
    _backups --> _backups_cleanup
    _backups_nexus_20260310_160218["<b>nexus_20260310_160218</b>"]
    class _backups_nexus_20260310_160218 support
    _backups --> _backups_nexus_20260310_160218
    _backups_nexus_20260310_160218_app["<b>app</b>"]
    class _backups_nexus_20260310_160218_app support
    _backups_nexus_20260310_160218 --> _backups_nexus_20260310_160218_app
    _backups_nexus_20260310_160218_app_application["<b>application</b>"]
    class _backups_nexus_20260310_160218_app_application support
    _backups_nexus_20260310_160218_app --> _backups_nexus_20260310_160218_app_application
    _backups_nexus_20260310_160218_app_application_services["<b>services</b><br/><hr/>📄 capability_gap_reporter.py: CapabilityGapReporter, execute<br/>📄 assistant_service.py: AssistantService"]
    class _backups_nexus_20260310_160218_app_application_services support
    _backups_nexus_20260310_160218_app_application --> _backups_nexus_20260310_160218_app_application_services
    _backups_nexus_20260310_160218_app_adapters["<b>adapters</b>"]
    class _backups_nexus_20260310_160218_app_adapters adapter
    _backups_nexus_20260310_160218_app --> _backups_nexus_20260310_160218_app_adapters
    _backups_nexus_20260310_160218_app_adapters_edge["<b>edge</b><br/><hr/>📄 worker_pc.py: main"]
    class _backups_nexus_20260310_160218_app_adapters_edge adapter
    _backups_nexus_20260310_160218_app_adapters --> _backups_nexus_20260310_160218_app_adapters_edge
    _backups_nexus_20260310_160218_app_adapters_infrastructure["<b>infrastructure</b><br/><hr/>📄 github_adapter.py: GitHubAdapter, execute<br/>📄 gateway_llm_adapter.py: GatewayLLMCommandAdapter, get_system_instruction<br/>📄 api_server.py: get_current_user, create_api_server, telegram_webhook"]
    class _backups_nexus_20260310_160218_app_adapters_infrastructure adapter
    _backups_nexus_20260310_160218_app_adapters --> _backups_nexus_20260310_160218_app_adapters_infrastructure
    _backups_nexus_20260310_160218_app_adapters_infrastructure_routers["<b>routers</b><br/><hr/>📄 github.py: create_github_router, github_worker_operation, auto_heal_ci_failure<br/>📄 evolution.py: create_evolution_router, get_evolution_status"]
    class _backups_nexus_20260310_160218_app_adapters_infrastructure_routers adapter
    _backups_nexus_20260310_160218_app_adapters_infrastructure --> _backups_nexus_20260310_160218_app_adapters_infrastructure_routers
    backups["<b>backups</b>"]
    class backups support
    skills["<b>skills</b>"]
    class skills support
    skills_jarvis-portas-browser["<b>jarvis-portas-browser</b>"]
    class skills_jarvis-portas-browser support
    skills --> skills_jarvis-portas-browser
    skills_jarvis-android-navigation["<b>jarvis-android-navigation</b>"]
    class skills_jarvis-android-navigation support
    skills --> skills_jarvis-android-navigation
    skills_jarvis-context-memory["<b>jarvis-context-memory</b>"]
    class skills_jarvis-context-memory support
    skills --> skills_jarvis-context-memory
    skills_jarvis-viv["<b>jarvis-viv</b>"]
    class skills_jarvis-viv support
    skills --> skills_jarvis-viv
    skills_jarvis-host-ops["<b>jarvis-host-ops</b>"]
    class skills_jarvis-host-ops support
    skills --> skills_jarvis-host-ops
    skills_jarvis-visual-navigation["<b>jarvis-visual-navigation</b>"]
    class skills_jarvis-visual-navigation support
    skills --> skills_jarvis-visual-navigation
    skills_jarvis-mobile-notifications["<b>jarvis-mobile-notifications</b>"]
    class skills_jarvis-mobile-notifications support
    skills --> skills_jarvis-mobile-notifications
    skills_jarvis-multi-agent-coordination["<b>jarvis-multi-agent-coordination</b>"]
    class skills_jarvis-multi-agent-coordination support
    skills --> skills_jarvis-multi-agent-coordination
    capabilities["<b>capabilities</b><br/><hr/>📄 classification.py: from, CapabilityStatus, class"]
    class capabilities support
    migrations["<b>migrations</b>"]
    class migrations support
    docs["<b>docs</b>"]
    class docs support
    docs_architecture["<b>architecture</b>"]
    class docs_architecture support
    docs --> docs_architecture
    docs_skills-connectors["<b>skills-connectors</b>"]
    class docs_skills-connectors support
    docs --> docs_skills-connectors
    supabase["<b>supabase</b>"]
    class supabase support
    supabase_migrations["<b>migrations</b>"]
    class supabase_migrations support
    supabase --> supabase_migrations
    supabase__temp["<b>.temp</b>"]
    class supabase__temp support
    supabase --> supabase__temp
    config["<b>config</b>"]
    class config support
    config_toolchains["<b>toolchains</b>"]
    class config_toolchains support
    config --> config_toolchains
    config_pipelines["<b>pipelines</b>"]
    class config_pipelines support
    config --> config_pipelines
    dags["<b>dags</b><br/><hr/>📄 jarvis_status_dag.py: get_assistant_status, send_notification"]
    class dags support
    app["<b>app</b><br/><hr/>📄 container.py: Container<br/>📄 bootstrap_edge.py: main"]
    class app support
    app_plugins["<b>plugins</b><br/><hr/>📄 plugin_loader.py: PluginLoader, execute"]
    class app_plugins support
    app --> app_plugins
    app_plugins_dynamic["<b>dynamic</b><br/><hr/>📄 example_plugin.py: hello_jarvis, register, PluginCapability"]
    class app_plugins_dynamic support
    app_plugins --> app_plugins_dynamic
    app_application["<b>application</b><br/><hr/>📄 return_activity_service.py: class, was_idle"]
    class app_application support
    app --> app_application
    app_application_security["<b>security</b><br/><hr/>📄 repository_path_policy.py: UnsafeRepositoryPath, normalize_relative_path, validate_filename<br/>📄 capability_authorizer.py: CapabilityAuthorizer, can_execute"]
    class app_application_security support
    app_application --> app_application_security
    app_application_communication["<b>communication</b><br/><hr/>📄 human_intervention.py: HumanIntervention, execute"]
    class app_application_communication support
    app_application --> app_application_communication
    app_application_services["<b>services</b><br/><hr/>📄 llm_router.py: LLMRouter, configure<br/>📄 assistant_learning.py: check_internal_solution, record_learning_interaction, infer_task_type<br/>📄 capability_manager.py: CapabilityManager, execute, implements<br/>📄 graph_enrichment.py: GraphEnrichmentService, enrich_scope<br/>📄 proactive_initiative_engine.py: from, InitiativeCandidate, to_dict<br/>📄 curiosity_intake.py: CuriosityIntake, configure<br/>📄 adapter_registry.py: from, CapabilityGap, ready<br/>📄 run_workflow.py: RunWorkflow, execute<br/>📄 tactical_map_service.py: TacticalMapService, execute<br/>📄 github_worker.py: GitHubWorker<br/>📄 structured_logger.py: StructuredLogger, execute<br/>📄 evolution_orchestrator.py: EvolutionOrchestrator, configure<br/>📄 device_service.py: DeviceService, execute<br/>📄 c2_orchestrator_service.py: KeepAliveProvider, start<br/>📄 device_intent_translator.py: DeviceIntentTranslator, can_execute, execute<br/>📄 surgical_edit_service.py: SurgicalEditService, apply_surgical_edit<br/>📄 intelligence_recurring_worker.py: from, IntelligenceWorkerConfig<br/>📄 meta_reflection.py: MetaReflection, configure<br/>📄 prioritizer_service.py: PrioritizerService, execute<br/>📄 capability_gap_reporter.py: CapabilityGapReporter, execute<br/>📄 graph_retention.py: GraphRetentionService, prune_scope<br/>📄 extension_manager.py: ExtensionManager, execute<br/>📄 location_service.py: LocationService, execute<br/>📄 finetune_dataset_collector.py: FineTuneDatasetCollector, configure<br/>📄 capability_blueprint_service.py: CapabilityBlueprintService, execute<br/>📄 osint_discovery.py: RateLimitExceeded, InMemoryTTLCache<br/>📄 status_service.py: StatusService, get_system_report<br/>📄 browser_manager.py: PersistentBrowserManager, execute<br/>📄 serve.py: setup_telegram_webhook<br/>📄 evolution_loop.py: EvolutionLoopService, configure<br/>📄 assistant_curiosity.py: maybe_inject_curiosity_question, capture_curiosity_answer<br/>📄 human_intervention_service.py: HumanInterventionService, execute<br/>📄 technical_analysis_service.py: TechnicalAnalysisService, execute<br/>📄 assistant_lifecycle.py: health_check_loop, start_service, stop_service<br/>📄 llm_capability_prompt_builder.py: extract_keywords, search_files_by_keywords, build_analysis_prompt<br/>📄 assistant_proactivity.py: maybe_get_proactive_suggestion<br/>📄 user_communication_service.py: from, CommunicationPriority, CommunicationDecision<br/>📄 evolution_sandbox.py: EvolutionSandbox, enabled<br/>📄 model_orchestrator.py: ModelOrchestrator, configure<br/>📄 thought_log_renderer.py: ThoughtRenderer, render<br/>📄 soldier_registry.py: SoldierRegistry, execute<br/>📄 orchestrator_service.py: OrchestratorService, execute<br/>📄 llm_capability_detector.py: LLMCapabilityDetector, execute<br/>📄 main.py: notify_online, run_api, background_bootstrap<br/>📄 evolution_gatekeeper.py: EvolutionGatekeeper, configure<br/>📄 osint_fusion.py: OSINTFusion, fuse<br/>📄 assistant_nexus.py: nexus_execute, nexus_can_execute, async_process_command<br/>📄 presence_service.py: from, PresenceState, PresenceSnapshot<br/>📄 osint_adapter_setup.py: configure_osint_adapters, get_osint_registry<br/>📄 evaluate_risks_service.py: EvaluateRisksService, execute<br/>📄 scavenger_hunt.py: logger, class, ScavengerHunt<br/>📄 thought_log_service.py: ThoughtLogService, create_thought<br/>📄 strategist_service.py: BudgetExceededException, StrategistService<br/>📄 vocal_orchestration_service.py: VocalOrchestrationService<br/>📄 device_orchestrator_service.py: SoldierDB, DeviceOrchestratorService<br/>📄 interface_bridge.py: InterfaceBridge, execute<br/>📄 roadmap_mission_selector.py: RoadmapManifestError, RoadmapMissionSelector<br/>📄 consolidated_context_service.py: ConsolidatedContextService, can_execute<br/>📄 finetune_trigger_service.py: FineTuneTriggerService, configure<br/>📄 laya_decision_shadow.py: LayaDecisionShadowObserver, submit<br/>📄 curiosity_engine.py: CuriosityEngine<br/>📄 memory_manager.py: MemoryManager, execute<br/>📄 agent_task_queue_service.py: TaskQueueUnavailable, AgentTaskQueueService<br/>📄 llm_service.py: LlmService, chat<br/>📄 dependency_manager.py: DependencyManager, ensure_capability<br/>📄 assistant_service.py: AssistantService<br/>📄 auto_evolutionV2.py: AutoEvolutionServiceV2, execute<br/>📄 local_repair_agent.py: LocalRepairAgent, execute<br/>📄 field_vision.py: FieldVision<br/>📄 reconnection_briefing.py: ReconnectionBriefing, execute<br/>📄 device_location_service.py: DeviceLocationService, execute, calculate_distance<br/>📄 device_capability_service.py: DeviceLocationService, calculate_distance<br/>📄 capability_impact_analyzer.py: CapabilityImpactAnalyzer, execute<br/>📄 metabolism_core.py: MetabolismCore, execute, ask_jarvis<br/>📄 thought_log_types.py: ThoughtType<br/>📄 graph_expander_setup.py: configure_graph_expanders, get_graph_expander_registry<br/>📄 notification_service.py: NotificationService, execute<br/>📄 memory_consolidation_service.py: MemoryConsolidationService<br/>📄 task_runner.py: TaskRunner<br/>📄 local_bridge.py: LocalBridgeManager, execute<br/>📄 capability_detectors.py: detect_capability_inventory, detect_capability_classification, detect_existing_capabilities_recognition<br/>📄 jrvs_translator.py: JrvsTranslator, execute<br/>📄 thought_log_storage.py: ThoughtLogStorage, db<br/>📄 graph_store_setup.py: graph_db_path, get_graph_store, reset_graph_store<br/>📄 intelligence_core.py: IntelligenceCore, process<br/>📄 identify_mission_critical_capabilities.py: identify_mission_critical_capabilities"]
    class app_application_services support
    app_application --> app_application_services
    app_application_services_jarvis_dev_agent["<b>jarvis_dev_agent</b><br/><hr/>📄 agent.py: JarvisDevAgent, configure"]
    class app_application_services_jarvis_dev_agent support
    app_application_services --> app_application_services_jarvis_dev_agent
    app_application_services_crystallization["<b>crystallization</b><br/><hr/>📄 crystallizer_engine.py: CrystallizerEngine, execute"]
    class app_application_services_crystallization support
    app_application_services --> app_application_services_crystallization
    app_application_privacy["<b>privacy</b><br/><hr/>📄 pii_redactor.py: PiiRedactor, execute"]
    class app_application_privacy support
    app_application --> app_application_privacy
    app_application_ports["<b>ports</b><br/><hr/>📄 visual_navigation.py: VisualNavigationPort, execute<br/>📄 model_runtime.py: from, ModelMessage<br/>📄 intelligence_source.py: IntelligenceSource, fetch_events<br/>📄 android_navigation.py: AndroidNavigationPort, observe_screen, tap<br/>📄 web_provider.py: WebProvider, execute, open_url<br/>📄 voice_provider.py: VoiceProvider, execute, speak<br/>📄 system_controller.py: SystemController, execute_command, is_available<br/>📄 osint_provider.py: OsintProvider, search<br/>📄 history_provider.py: HistoryProvider, execute, save_interaction<br/>📄 graph_store.py: from, UpsertReport, total<br/>📄 osint_discovery.py: GeoProvider, locate, NetworkResolver<br/>📄 action_provider.py: ActionProvider, execute, type_text<br/>📄 memory_provider.py: MemoryProvider, execute, store_event<br/>📄 soldier_provider.py: SoldierProvider, execute, register_soldier<br/>📄 security_provider.py: SecurityProvider, execute, verify_password<br/>📄 intelligence_history_repository.py: IntelligenceHistoryRepository, persist<br/>📄 intelligence_observation_source.py: IntelligenceObservationSource, collect_observations<br/>📄 decision_engine.py: DecisionEngine, decide<br/>📄 reward_provider.py: RewardProvider, execute, log_reward<br/>📄 vector_memory_store.py: VectorMemoryStore, is_available, is_healthy<br/>📄 tactical_command_port.py: TacticalCommandPort, execute, execute_security_payload"]
    class app_application_ports port
    app_application --> app_application_ports
    app_static["<b>static</b>"]
    class app_static support
    app --> app_static
    app_adapters["<b>adapters</b><br/><hr/>📄 jarvis_return_activity.py: LASTINPUTINFO, get_idle_seconds"]
    class app_adapters adapter
    app --> app_adapters
    app_adapters_edge["<b>edge</b><br/><hr/>📄 mdns_discovery_adapter.py: parse_mdns_response, discover_mdns<br/>📄 voice_engine.py: JarvisEngine, execute<br/>📄 active_recruiter_adapter.py: ActiveRecruiterAdapter, execute<br/>📄 jarvis_local_agent.py: JarvisLocalAgent, execute<br/>📄 worker_pc.py: main<br/>📄 environment_observation_publisher.py: build_desktop_observations, publish_observation, configured_observation_target<br/>📄 windows_etw_network_adapter.py: parse_tracerpt_xml<br/>📄 android_navigation_adapter.py: AndroidNavigationAdapter<br/>📄 osint_mcp_tools.py: register_osint_tools, provider<br/>📄 portas_midia.py: is_media_request<br/>📄 portas_midia_entrega.py: class, class, MediaDeliveryBus<br/>📄 jarvis_geospatial_intelligence.py: distance_km, filter_assets_by_radius<br/>📄 screen_coordinates.py: normalized_to_screen_point, enable_windows_per_monitor_dpi_awareness, screen_coordinate_spaces_compatible<br/>📄 web_adapter.py: WebAdapter, execute<br/>📄 portas_utilizacao.py: executar_porta, porta<br/>📄 portas_visualizacao.py: registrar_visualizacao_portas, portas_listar<br/>📄 jarvis_daily_briefing.py: weather_label, geocode_enabled<br/>📄 jarvis_device_registry.py: devices_db_path, ip_geolocation_enabled<br/>📄 jarvis_desktop_shell.py: normalize_cloud_url, build_start_url<br/>📄 host_resource_diagnostics.py: collect_host_resource_diagnostics<br/>📄 hardware_controller.py: HardwareController, execute<br/>📄 voice_adapter.py: VoiceAdapter, execute<br/>📄 security_audit_adapter.py: TacticalCommandPort, NearbyDevice<br/>📄 network_discovery_adapter.py: network_interfaces<br/>📄 jarvis_linux_mcp.py: create_app, lifespan, main<br/>📄 combined_voice_provider.py: CombinedVoiceProvider, execute<br/>📄 automation_adapter.py: AutomationAdapter, execute<br/>📄 keyboard_adapter.py: KeyboardAdapter, execute, type_text<br/>📄 navigation_gps.py: from, RouteStep, Route<br/>📄 background_window_input.py: pack_point, click_window_background, enum_callback<br/>📄 portas_observabilidade.py: sanitizar_url, sanitizar_payload<br/>📄 host_storage_diagnostics.py: collect_host_storage_diagnostics<br/>📄 tts_adapter.py: TTSAdapter, execute<br/>📄 portas_core.py: configurar_cdp_url, carregar_macros<br/>📄 jarvis_desktop_mcp.py: jarvis_agent_bootstrap, curiosity_capture<br/>📄 macrodroid_adapter.py: MacroDroidAdapter, can_execute"]
    class app_adapters_edge adapter
    app_adapters --> app_adapters_edge
    app_adapters_edge_host["<b>host</b><br/><hr/>📄 psutil_host_adapter.py: PsutilHostAdapter, get_identity"]
    class app_adapters_edge_host adapter
    app_adapters_edge --> app_adapters_edge_host
    app_adapters_infrastructure["<b>infrastructure</b><br/><hr/>📄 api_models.py: RequestSource, RequestMetadata, ExecuteRequest<br/>📄 soldier_bridge.py: SoldierBridgeManager, connect<br/>📄 reward_adapter.py: RewardAdapter, execute<br/>📄 respan_tracing.py: initialize_respan_tracing, shutdown_respan_tracing<br/>📄 mqtt_home_adapter.py: MqttHomeAdapter, execute<br/>📄 auth_adapter.py: AuthAdapter, execute<br/>📄 overwatch_adapter.py: OverwatchDaemon, execute<br/>📄 jrvs_cloud_storage.py: JrvsCloudStorage, execute<br/>📄 playwright_worker.py: PlaywrightWorker, start<br/>📄 github_adapter.py: GitHubAdapter, execute<br/>📄 websocket_manager.py: WebSocketManager, execute<br/>📄 github_issue_mixin.py: GitHubIssueMixin, provides, execute<br/>📄 pyinstaller_builder.py: PyinstallerBuilder, configure, can_execute<br/>📄 consolidator.py: NexusComponent, Consolidator<br/>📄 http_client.py: HttpClient<br/>📄 agent_worker_credentials.py: from, worker_token_env_name, AgentWorkerPrincipal<br/>📄 gateway_llm_adapter.py: GatewayLLMCommandAdapter, get_system_instruction<br/>📄 github_correction_adapter.py: GitHubCorrectionAdapter<br/>📄 socket_client.py: SocketClient, execute<br/>📄 ai_gateway.py: AIGateway<br/>📄 supabase_client.py: get_supabase_client, is_supabase_available, get_supabase_admin_client<br/>📄 docker_sandbox.py: DockerSandbox, run_tests<br/>📄 github_issue_adapter.py: GitHubIssueAdapter, execute<br/>📄 tool_approval_store.py: ToolApprovalStore<br/>📄 gemini_adapter.py: LLMCommandAdapter, execute<br/>📄 telegram_adapter.py: TelegramAdapter<br/>📄 gist_uploader.py: GistUploader, execute<br/>📄 ai_gateway_enums.py: LLMProvider, GroqGear, AIGatewayEnums<br/>📄 supabase_plan_journal.py: SupabasePlanEventJournal, append<br/>📄 gemini_context_manager.py: GeminiContextManager, execute<br/>📄 action_provider.py: ActionProvider, execute<br/>📄 host_ops.py: from, PathNotAllowed<br/>📄 ai_gateway_token_utils.py: count_tokens, TokenCounter<br/>📄 auto_repair_mixin.py: AutoRepairMixin, must, execute<br/>📄 dummy_voice_provider.py: DummyVoiceProvider, execute<br/>📄 reward_logger.py: RewardLogger, execute<br/>📄 vision_adapter.py: ExternalVisionNotAllowedError, VisionAdapter<br/>📄 sqlite_history_adapter.py: CoercingUTCDateTime, process_bind_param<br/>📄 api_server.py: get_current_user, create_api_server, lifespan<br/>📄 setup_wizard.py: Colors, execute, print_header<br/>📄 ollama_adapter.py: OllamaAdapter, configure<br/>📄 system_executor.py: SystemExecutor, configure, can_execute<br/>📄 persistent_shell_adapter.py: PersistentShellAdapter, configure<br/>📄 mcp_bearer_auth.py: BearerAuthMiddleware<br/>📄 drive_uploader.py: DriveUploader, configure<br/>📄 github_workflow_adapter.py: GitHubWorkflowAdapter, execute<br/>📄 copilot_context_provider.py: GitHubCopilotContextProvider, execute, analyzes<br/>📄 secure_shell_navigation.py: ShellNavigator<br/>📄 cost_tracker_adapter.py: CostTrackerAdapter<br/>📄 audit_logger.py: AuditLogger, configure, execute<br/>📄 gemini_response_helpers.py: build_context_message, build_parameters, convert_function_call_to_intent<br/>📄 freellmapi_model_runtime.py: FreeLLMAPIModelRuntimeAdapter, invoke<br/>📄 supabase_vector_memory_store.py: SupabaseVectorMemoryStore, is_available<br/>📄 host_ops_mcp_tools.py: register_host_ops_tools"]
    class app_adapters_infrastructure adapter
    app_adapters --> app_adapters_infrastructure
    app_adapters_infrastructure_routers["<b>routers</b><br/><hr/>📄 missions.py: create_missions_router, execute_mission, control_browser<br/>📄 mobile_push.py: MobileDeviceRegistration, MobileDeviceRevoke, MobileAgentNotification<br/>📄 github.py: create_github_router, github_worker_operation, auto_heal_ci_failure<br/>📄 extensions.py: create_extensions_router, install_package, get_package_status<br/>📄 mobile_sessions.py: MobileLoginRequest, MobileRefreshRequest, MobileRevokeRequest<br/>📄 devices.py: create_devices_router, register_device<br/>📄 google_identity.py: GoogleLoginRequest<br/>📄 agent_tasks.py: AgentHeartbeatRequest, EnqueueTaskRequest<br/>📄 evolution.py: create_evolution_router, get_evolution_status<br/>📄 network_discovery.py: DeviceInspectionRequest, CameraDiscoveryRequest, MdnsDiscoveryRequest<br/>📄 assistant.py: create_assistant_router<br/>📄 environment_observations.py: EnvironmentObservationCreate, Config, validate_device_id<br/>📄 health.py: create_health_router, health_check, health_detail<br/>📄 bridge.py: create_bridge_router, require_authenticated_principal, local_bridge_websocket<br/>📄 admin_recovery.py: AdminPasswordResetRequest, create_admin_recovery_router<br/>📄 github_webhook.py: verify_github_signature, create_github_webhook_router, receive_github_webhook<br/>📄 thoughts.py: create_thoughts_router, create_thought_log<br/>📄 utility.py: create_utility_router, get_api_key_guides, analyze_missing_resources<br/>📄 dev_agent.py: create_dev_agent_router, run_dev_agent, list_dev_agent_jobs"]
    class app_adapters_infrastructure_routers adapter
    app_adapters_infrastructure --> app_adapters_infrastructure_routers
    app_adapters_infrastructure_secrets["<b>secrets</b><br/><hr/>📄 env_secrets_provider.py: EnvSecretsProvider, execute, get_secret"]
    class app_adapters_infrastructure_secrets adapter
    app_adapters_infrastructure --> app_adapters_infrastructure_secrets
    app_adapters_infrastructure_graph["<b>graph</b><br/><hr/>📄 sensitive_store.py: SQLiteSensitiveStore"]
    class app_adapters_infrastructure_graph adapter
    app_adapters_infrastructure --> app_adapters_infrastructure_graph
    app_adapters_infrastructure_osint["<b>osint</b><br/><hr/>📄 eagle_osint_adapter.py: EagleOsintAdapter<br/>📄 censys_adapter.py: CensysAdapter, query_radius<br/>📄 ipinfo_adapter.py: IPInfoAdapter, locate<br/>📄 shodan_adapter.py: ShodanAdapter, query_radius<br/>📄 wigle_adapter.py: WigleAdapter, query_radius"]
    class app_adapters_infrastructure_osint adapter
    app_adapters_infrastructure --> app_adapters_infrastructure_osint
    app_adapters_infrastructure_intelligence["<b>intelligence</b><br/><hr/>📄 supabase_intelligence_history_adapter.py: SupabaseIntelligenceHistoryAdapter<br/>📄 public_intelligence_adapter.py: PublicIntelligenceAdapter<br/>📄 supabase_intelligence_worker_store.py: SupabaseIntelligenceWorkerStore<br/>📄 supabase_intelligence_history.py: IntelligenceHistoryPersistenceError, SupabaseIntelligenceHistoryAdapter<br/>📄 laya_decision_adapter.py: LayaDecisionError, LayaDecisionAdapter"]
    class app_adapters_infrastructure_intelligence adapter
    app_adapters_infrastructure --> app_adapters_infrastructure_intelligence
    app_adapters_api["<b>api</b><br/><hr/>📄 voice_endpoint.py: voice_stream"]
    class app_adapters_api adapter
    app_adapters --> app_adapters_api
    app_runtime["<b>runtime</b><br/><hr/>📄 pipeline_runner.py: CloudMock, run_pipeline"]
    class app_runtime support
    app --> app_runtime
    app_runtime_toolbox["<b>toolbox</b><br/><hr/>📄 authorization.py: ToolAuthorizationPolicy, authorize_tool<br/>📄 audit.py: JsonlToolAuditSink<br/>📄 toolchains.py: ToolchainStep, ToolchainManifest, from_file<br/>📄 contracts.py: ToolRequest, ToolResult, ToolAuthorizationDecision<br/>📄 host_authorization.py: TrustedToolPrincipal, validate_identity_fields, validate_capability_grants"]
    class app_runtime_toolbox support
    app_runtime --> app_runtime_toolbox
    app_domain["<b>domain</b>"]
    class app_domain support
    app --> app_domain
    app_domain_gears["<b>gears</b><br/><hr/>📄 cognitive_router.py: CognitiveRouter, configure<br/>📄 llm_engine.py: LlmEngine, configure"]
    class app_domain_gears support
    app_domain --> app_domain_gears
    app_domain_context["<b>context</b><br/><hr/>📄 context_manager.py: SystemContext, ContextManager"]
    class app_domain_context support
    app_domain --> app_domain_context
    app_domain_analysis["<b>analysis</b><br/><hr/>📄 performance_analyzer.py: PerformanceAnalyzer, execute"]
    class app_domain_analysis support
    app_domain --> app_domain_analysis
    app_domain_services["<b>services</b><br/><hr/>📄 agent_service.py: AgentService, execute<br/>📄 command_interpreter.py: CommandInterpreter, execute<br/>📄 safety_guardian.py: SafetyGuardian, configure<br/>📄 vocal_orchestrator.py: VocalOrchestrator, execute<br/>📄 state_manager.py: StateManager, execute<br/>📄 soldier_shield.py: SoldierShield, execute<br/>📄 system_state_tracker.py: SystemStateTracker, execute<br/>📄 llm_command_interpreter.py: LLMCommandInterpreter, execute<br/>📄 intent_processor.py: IntentProcessor<br/>📄 reward_signal_provider.py: record"]
    class app_domain_services support
    app_domain --> app_domain_services
    app_domain_ai["<b>ai</b><br/><hr/>📄 gemini_service.py: GeminiService, execute"]
    class app_domain_ai support
    app_domain --> app_domain_ai
    app_domain_capabilities["<b>capabilities</b><br/><hr/>📄 cap_094.py: Cap094, execute<br/>📄 cap_011.py: Cap011, execute<br/>📄 cap_057.py: Cap057, configure<br/>📄 cap_073.py: Cap073, execute<br/>📄 cap_058.py: Cap058, execute<br/>📄 cap_032.py: Cap032, configure<br/>📄 cap_014.py: Cap014, execute<br/>📄 cap_071.py: Cap071, execute<br/>📄 cap_093.py: Cap093, execute<br/>📄 cap_012.py: Cap012, execute<br/>📄 cap_046.py: Cap046, execute<br/>📄 cap_019.py: Cap019, execute<br/>📄 cap_068.py: Cap068, execute<br/>📄 cap_049.py: Cap049, execute<br/>📄 cap_007.py: Cap007, configure<br/>📄 cap_063.py: Cap063, execute<br/>📄 cap_054.py: Cap054, execute<br/>📄 cap_044.py: Cap044, configure<br/>📄 cap_038.py: Cap038, execute<br/>📄 cap_047.py: Cap047, configure<br/>📄 cap_002.py: Cap002, configure<br/>📄 cap_018.py: Cap018, execute<br/>📄 cap_053.py: Cap053, execute<br/>📄 cap_066.py: Cap066, execute<br/>📄 cap_005.py: Cap005, configure<br/>📄 cap_039.py: Cap039, configure<br/>📄 cap_008.py: Cap008, configure<br/>📄 cap_084.py: Cap084, execute<br/>📄 cap_060.py: Cap060, execute<br/>📄 cap_043.py: Cap043, execute<br/>📄 cap_028.py: Cap028, execute<br/>📄 cap_051.py: Cap051, execute<br/>📄 cap_061.py: Cap061, execute<br/>📄 cap_001.py: Cap001, configure<br/>📄 cap_042.py: Cap042, execute<br/>📄 cap_076.py: Cap076, execute<br/>📄 cap_062.py: Cap062, execute<br/>📄 cap_085.py: Cap085, execute<br/>📄 cap_022.py: Cap022, execute<br/>📄 cap_091.py: Cap091, execute<br/>📄 cap_021.py: Cap021, execute<br/>📄 cap_033.py: Cap033, configure<br/>📄 cap_029.py: Cap029, execute<br/>📄 cap_052.py: Cap052, execute<br/>📄 cap_004.py: Cap004, configure<br/>📄 cap_056.py: Cap056, execute<br/>📄 context_memory.py: ContextMemory, configure, execute<br/>📄 cap_083.py: Cap083, execute<br/>📄 cap_075.py: Cap075, execute<br/>📄 cap_090.py: Cap090, execute<br/>📄 cap_095.py: Cap095, configure<br/>📄 cap_069.py: Cap069, execute<br/>📄 cap_067.py: Cap067, configure<br/>📄 cap_009.py: Cap009, execute<br/>📄 cap_050.py: Cap050, execute<br/>📄 cap_024.py: Cap024, execute<br/>📄 cap_037.py: Cap037, execute<br/>📄 cap_048.py: Cap048, execute<br/>📄 cap_041.py: Cap041, execute<br/>📄 cap_010.py: Cap010, execute<br/>📄 cap_077.py: Cap077, execute<br/>📄 cap_072.py: Cap072, configure<br/>📄 cap_082.py: Cap082, execute<br/>📄 cap_016.py: Cap016, execute<br/>📄 cap_100.py: Cap100, configure<br/>📄 cap_098.py: Cap098, execute<br/>📄 cap_040.py: Cap040, configure<br/>📄 cap_035.py: Cap035, execute<br/>📄 cap_064.py: Cap064, execute<br/>📄 cap_078.py: Cap078, execute<br/>📄 cap_097.py: Cap097, execute<br/>📄 cap_087.py: Cap087, execute<br/>📄 cap_030.py: Cap030, execute<br/>📄 cap_017.py: Cap017, execute<br/>📄 cap_079.py: Cap079, execute<br/>📄 cap_080.py: Cap080, execute<br/>📄 cap_031.py: Cap031, execute<br/>📄 cap_003.py: Cap003, configure<br/>📄 cap_045.py: Cap045, configure<br/>📄 cap_086.py: Cap086, execute<br/>📄 cap_059.py: Cap059, configure<br/>📄 cap_088.py: Cap088, execute<br/>📄 cap_023.py: Cap023, configure<br/>📄 cap_074.py: Cap074, execute<br/>📄 cap_101.py: Cap101, execute<br/>📄 cap_102.py: Cap102, execute<br/>📄 cap_013.py: Cap013, execute<br/>📄 cap_026.py: Cap026, execute<br/>📄 cap_015.py: Cap015, execute<br/>📄 cap_089.py: Cap089, execute<br/>📄 cap_070.py: Cap070, execute<br/>📄 cap_006.py: Cap006, configure<br/>📄 cap_020.py: Cap020, execute<br/>📄 cap_081.py: Cap081, execute<br/>📄 cap_065.py: Cap065, execute<br/>📄 cap_036.py: Cap036, execute<br/>📄 cap_055.py: Cap055, execute<br/>📄 cap_034.py: Cap034, configure<br/>📄 cap_027.py: Cap027, configure<br/>📄 cap_092.py: Cap092, execute<br/>📄 cap_096.py: Cap096, execute<br/>📄 cap_025.py: Cap025, execute<br/>📄 cap_099.py: Cap099, execute"]
    class app_domain_capabilities support
    app_domain --> app_domain_capabilities
    app_domain_missions["<b>missions</b><br/><hr/>📄 mission_selector.py: MissionSelector, execute"]
    class app_domain_missions support
    app_domain --> app_domain_missions
    app_domain_models["<b>models</b><br/><hr/>📄 device.py: Device, execute, Capability<br/>📄 adapter_registry.py: class, to_dict, AdapterRegistry<br/>📄 capability.py: JarvisCapability, execute<br/>📄 evolution_reward.py: EvolutionReward, execute<br/>📄 mission.py: class, execute, to_dict<br/>📄 capability_alias_registry.py: from, AliasRegistryError, UnknownAliasError<br/>📄 thought_log.py: InteractionStatus, ThoughtLog, Config<br/>📄 agent.py: ActionType, TaskSource, TaskPriority<br/>📄 soldier.py: SoldierStatus, SoldierRegistration, soldier_id_not_empty<br/>📄 command.py: CommandType, Intent<br/>📄 system_state.py: SystemStatus, execute, Config<br/>📄 viability.py: RiskLevel, ImpactLevel, class"]
    class app_domain_models support
    app_domain --> app_domain_models
    app_domain_ports["<b>ports</b><br/><hr/>📄 device_control_port.py: from, class, DeviceControlPort<br/>📄 host_port.py: from, HostIdentity, DiskUsage"]
    class app_domain_ports port
    app_domain --> app_domain_ports
    app_domain_orchestration["<b>orchestration</b><br/><hr/>📄 central_orchestrator.py: CentralOrchestrator, execute"]
    class app_domain_orchestration support
    app_domain --> app_domain_orchestration
    app_domain_graph["<b>graph</b><br/><hr/>📄 edges.py: PivotType, edge_id, Edge<br/>📄 registry.py: from, GapReport, ready<br/>📄 confidence.py: is_strong_pivot, edge_confidence<br/>📄 nodes.py: NodeType, only_digits<br/>📄 graph.py: GraphIntegrityError, GraphDelta<br/>📄 pruner.py: PrunePolicy, ttl_for<br/>📄 sensitive_store.py: utcnow, as_utc, AccessRecord<br/>📄 resolver.py: AdapterBoundaryError<br/>📄 loop.py: from, LoopPolicy<br/>📄 fuse.py: haversine_km, Fuse<br/>📄 expander.py: from, ExpansionCost, Expansion<br/>📄 policy.py: from, GraphPolicyError, for"]
    class app_domain_graph support
    app_domain --> app_domain_graph
    app_domain_intelligence["<b>intelligence</b><br/><hr/>📄 osint.py: Coordinate, finite_values, NetworkRange<br/>📄 contracts.py: GeoPoint, IntelligenceEvidence, IntelligenceEvent"]
    class app_domain_intelligence support
    app_domain --> app_domain_intelligence
    app_domain_tools["<b>tools</b><br/><hr/>📄 registry.py: DuplicateToolManifestError, ToolRegistry<br/>📄 contracts.py: HealthPolicy, validate_periodic_interval, RateLimitPolicy"]
    class app_domain_tools support
    app_domain --> app_domain_tools
    app_domain_memory["<b>memory</b><br/><hr/>📄 semantic_memory.py: SemanticMemory, configure<br/>📄 prospective_memory.py: ProspectiveMemory<br/>📄 working_memory.py: WorkingMemoryEntry, WorkingMemory"]
    class app_domain_memory support
    app_domain --> app_domain_memory
    app_ports["<b>ports</b><br/><hr/>📄 voice_port.py: VoicePort, stt, tts<br/>📄 secrets_provider.py: SecretsProvider, get_secret"]
    class app_ports port
    app --> app_ports
    app_multiagent["<b>multiagent</b><br/><hr/>📄 priority_queue_mini_agent.py: PriorityQueueMiniAgent, from_env<br/>📄 worker.py: AcknowledgingConnector, send, receive<br/>📄 agent_worker_runtime.py: run_worker_loop, WorkerGroup<br/>📄 execution_plan.py: from, PlanValidationError, StepOutcome<br/>📄 model_plan_adapter.py: extract_json_object, repair_model_plan<br/>📄 scheduler.py: from, NoEligibleAgentError<br/>📄 supabase_task_worker.py: SupabaseTaskQueueMiniAgent, from_env<br/>📄 model_runtime_factory.py: create_registered_model_handler<br/>📄 freellmapi_client.py: configured_provider_id, FreeLLMAPIError<br/>📄 model_registry.py: ModelProfile<br/>📄 freellmapi_handler.py: FreeLLMAgentHandler<br/>📄 transport.py: AgentMessage, create, to_dict<br/>📄 supabase_queue.py: SupabaseQueueConnector, send<br/>📄 leader.py: from, class, AgentLeader<br/>📄 contracts.py: TaskStatus, AgentProfile<br/>📄 supabase_store.py: SupabaseAgentStore, register_agent"]
    class app_multiagent support
    app --> app_multiagent
    app_utils["<b>utils</b><br/><hr/>📄 jrvs_codec.py: JrvsDecodeError, encode, decode<br/>📄 document_store.py: DocumentStore, read, write<br/>📄 helpers.py: setup_logging, ensure_directory, sanitize_filename"]
    class app_utils support
    app --> app_utils
    app_core["<b>core</b><br/><hr/>📄 nexus.py: JarvisNexus<br/>📄 recovery_store.py: RecoveryError<br/>📄 operating_profiles.py: from, OperatingProfile<br/>📄 nexus_exceptions.py: ImportTimeoutError, InstantiateTimeoutError, instantiation<br/>📄 config.py: Settings, decrypt_api_key, decrypt_database_url<br/>📄 encryption.py: get_hardware_id, derive_key_from_hardware, encrypt_value<br/>📄 llm_config.py: LLMConfig, use_llm_command_interpretation, use_llm_capability_detection<br/>📄 nexuscomponent.py: NexusComponent<br/>📄 nexus_discovery.py: finders"]
    class app_core core
    app --> app_core
    app_core_meta["<b>meta</b><br/><hr/>📄 jrvs_compiler.py: SchemaVersionError, JRVSCompiler<br/>📄 compile_lock.py: acquire_compile_lock<br/>📄 policy_store.py: PolicyStore, get_policies_by_module<br/>📄 exploration_controller.py: ExplorationController, execute<br/>📄 decision_engine.py: class, DecisionEngine"]
    class app_core_meta core
    app_core --> app_core_meta
    _agents["<b>.agents</b>"]
    class _agents support
    _agents_skills["<b>skills</b>"]
    class _agents_skills support
    _agents --> _agents_skills
    _agents_skills_jarvis-android-navigation["<b>jarvis-android-navigation</b>"]
    class _agents_skills_jarvis-android-navigation support
    _agents_skills --> _agents_skills_jarvis-android-navigation
    _agents_skills_jarvis-context-memory["<b>jarvis-context-memory</b>"]
    class _agents_skills_jarvis-context-memory support
    _agents_skills --> _agents_skills_jarvis-context-memory
    _agents_skills_jarvis-visual-navigation["<b>jarvis-visual-navigation</b>"]
    class _agents_skills_jarvis-visual-navigation support
    _agents_skills --> _agents_skills_jarvis-visual-navigation
    _agents_skills_jarvis-mobile-notifications["<b>jarvis-mobile-notifications</b>"]
    class _agents_skills_jarvis-mobile-notifications support
    _agents_skills --> _agents_skills_jarvis-mobile-notifications
    _agents_skills_jarvis-multi-agent-coordination["<b>jarvis-multi-agent-coordination</b>"]
    class _agents_skills_jarvis-multi-agent-coordination support
    _agents_skills --> _agents_skills_jarvis-multi-agent-coordination
```
