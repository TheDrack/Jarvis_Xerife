# 🏗️ JARVIS_Xerife: Mapa de Arquitetura Dinâmico
> **Protocolo de Simbiose:** Documentação gerada via análise de código real.

```mermaid
graph LR
    classDef core fill:#1a1f25,stroke:#00ff00,color:#fff,stroke-width:2px;
    classDef adapter fill:#1a1f25,stroke:#007bff,color:#fff;
    classDef port fill:#1a1f25,stroke:#ffa500,color:#fff,stroke-dasharray: 5 5;
    classDef support fill:#2d333b,stroke:#6c757d,color:#aaa;
    capabilities["<b>capabilities</b><br/><hr/>📄 classification.py: from, CapabilityStatus, class"]
    class capabilities support
    docs["<b>docs</b>"]
    class docs support
    static["<b>static</b>"]
    class static support
    backups["<b>backups</b>"]
    class backups support
    dags["<b>dags</b><br/><hr/>📄 jarvis_status_dag.py: get_assistant_status, send_notification"]
    class dags support
    config["<b>config</b>"]
    class config support
    config_pipelines["<b>pipelines</b>"]
    class config_pipelines support
    config --> config_pipelines
    app["<b>app</b><br/><hr/>📄 bootstrap_edge.py: main<br/>📄 container.py: Container"]
    class app support
    app_static["<b>static</b>"]
    class app_static support
    app --> app_static
    app_application["<b>application</b>"]
    class app_application support
    app --> app_application
    app_application_services["<b>services</b><br/><hr/>📄 evolution_sandbox.py: EvolutionSandbox, enabled<br/>📄 status_service.py: StatusService, get_system_report<br/>📄 device_intent_translator.py: DeviceIntentTranslator, can_execute, execute<br/>📄 thought_log_types.py: ThoughtType<br/>📄 structured_logger.py: StructuredLogger, execute<br/>📄 device_capability_service.py: DeviceLocationService, calculate_distance, DeviceCapabilityService<br/>📄 capability_gap_reporter.py: CapabilityGapReporter, execute<br/>📄 technical_analysis_service.py: TechnicalAnalysisService, execute<br/>📄 device_orchestrator_service.py: SoldierDB, DeviceOrchestratorService<br/>📄 strategist_service.py: BudgetExceededException, StrategistService<br/>📄 assistant_learning.py: check_internal_solution, record_learning_interaction, infer_task_type<br/>📄 notification_service.py: NotificationService, execute<br/>📄 run_workflow.py: RunWorkflow, execute<br/>📄 model_orchestrator.py: ModelOrchestrator, configure<br/>📄 llm_service.py: LlmService, chat<br/>📄 assistant_lifecycle.py: health_check_loop, start_service, stop_service<br/>📄 main.py: MainService<br/>📄 assistant_curiosity.py: maybe_inject_curiosity_question, capture_curiosity_answer<br/>📄 assistant_nexus.py: nexus_execute, nexus_can_execute, async_process_command<br/>📄 memory_manager.py: MemoryManager, execute<br/>📄 interface_bridge.py: InterfaceBridge, execute<br/>📄 jarvis_dev_agent.py: JarvisDevAgent<br/>📄 scavenger_hunt.py: logger, class, ScavengerHunt<br/>📄 thought_log_service.py: ThoughtLogService, can_execute<br/>📄 evaluate_risks_service.py: EvaluateRisksService, execute<br/>📄 assistant_service.py: AssistantService<br/>📄 curiosity_engine.py: CuriosityEngine<br/>📄 human_intervention_service.py: HumanInterventionService, execute<br/>📄 tactical_map_service.py: TacticalMapService, execute<br/>📄 capability_detectors.py: detect_capability_inventory, detect_capability_classification, detect_existing_capabilities_recognition<br/>📄 device_location_service.py: DeviceLocationService, execute, calculate_distance<br/>📄 metabolism_core.py: MetabolismCore<br/>📄 thought_log_storage.py: ThoughtLogStorage, db<br/>📄 task_runner.py: TaskRunner, execute_mission<br/>📄 capability_impact_analyzer.py: CapabilityImpactAnalyzer, execute<br/>📄 llm_router.py: LLMRouter, configure<br/>📄 serve.py: setup_telegram_webhook<br/>📄 orchestrator_service.py: OrchestratorService, execute<br/>📄 auto_evolutionV2.py: AutoEvolutionServiceV2, execute<br/>📄 finetune_dataset_collector.py: FineTuneDatasetCollector, execute<br/>📄 memory_consolidation_service.py: MemoryConsolidationService<br/>📄 consolidated_context_service.py: ConsolidatedContextService, can_execute<br/>📄 llm_capability_detector.py: LLMCapabilityDetector, execute<br/>📄 capability_blueprint_service.py: CapabilityBlueprintService, execute<br/>📄 dependency_manager.py: DependencyManager, ensure_capability<br/>📄 extension_manager.py: ExtensionManager, execute<br/>📄 finetune_trigger_service.py: FineTuneTriggerService, configure<br/>📄 jrvs_translator.py: JrvsTranslator, execute<br/>📄 local_bridge.py: LocalBridgeManager, execute<br/>📄 evolution_loop.py: EvolutionLoopService, configure<br/>📄 prioritizer_service.py: PrioritizerService, execute<br/>📄 llm_capability_prompt_builder.py: extract_keywords, search_files_by_keywords, build_analysis_prompt<br/>📄 assistant_proactivity.py: maybe_get_proactive_suggestion<br/>📄 surgical_edit_service.py: SurgicalEditService, apply_surgical_edit<br/>📄 identify_mission_critical_capabilities.py: identify_mission_critical_capabilities<br/>📄 evolution_orchestrator.py: task, decorator, perform_self_healing_workflow<br/>📄 github_worker.py: GitHubWorker<br/>📄 evolution_gatekeeper.py: EvolutionGatekeeper, configure<br/>📄 meta_reflection.py: MetaReflection, configure<br/>📄 field_vision.py: FieldVision<br/>📄 browser_manager.py: PersistentBrowserManager, execute<br/>📄 vocal_orchestration_service.py: VocalOrchestrationService<br/>📄 capability_manager.py: CapabilityManager, execute, implements<br/>📄 c2_orchestrator_service.py: KeepAliveProvider, start<br/>📄 device_service.py: DeviceService, execute<br/>📄 local_repair_agent.py: LocalRepairAgent, execute<br/>📄 soldier_registry.py: SoldierRegistry, execute<br/>📄 thought_log_renderer.py: ThoughtRenderer, render<br/>📄 location_service.py: LocationService, execute"]
    class app_application_services support
    app_application --> app_application_services
    app_application_services_jarvis_dev_agent["<b>jarvis_dev_agent</b><br/><hr/>📄 code_discovery.py: CodeDiscovery<br/>📄 pipeline_builder.py: PipelineBuilder<br/>📄 trajectory.py: AgentTrajectory, add_step<br/>📄 actions.py: ActionExecutor<br/>📄 agent.py: JarvisDevAgent<br/>📄 prompt_builder.py: PromptBuilder"]
    class app_application_services_jarvis_dev_agent support
    app_application_services --> app_application_services_jarvis_dev_agent
    app_application_services_crystallization["<b>crystallization</b><br/><hr/>📄 crystallizer_engine.py: CrystallizerEngine, execute"]
    class app_application_services_crystallization support
    app_application_services --> app_application_services_crystallization
    app_application_security["<b>security</b><br/><hr/>📄 capability_authorizer.py: CapabilityAuthorizer, can_execute"]
    class app_application_security support
    app_application --> app_application_security
    app_application_communication["<b>communication</b><br/><hr/>📄 human_intervention.py: HumanIntervention, execute"]
    class app_application_communication support
    app_application --> app_application_communication
    app_application_privacy["<b>privacy</b><br/><hr/>📄 pii_redactor.py: PiiRedactor, execute"]
    class app_application_privacy support
    app_application --> app_application_privacy
    app_application_ports["<b>ports</b><br/><hr/>📄 voice_provider.py: VoiceProvider, execute, speak<br/>📄 system_controller.py: SystemController, execute_command, is_available<br/>📄 web_provider.py: WebProvider, execute, open_url<br/>📄 history_provider.py: HistoryProvider, execute, save_interaction<br/>📄 reward_provider.py: RewardProvider, execute, log_reward<br/>📄 osint_provider.py: OsintProvider, search<br/>📄 tactical_command_port.py: TacticalCommandPort, execute, execute_security_payload<br/>📄 memory_provider.py: MemoryProvider, execute, store_event<br/>📄 action_provider.py: ActionProvider, execute, type_text<br/>📄 soldier_provider.py: SoldierProvider, execute, register_soldier<br/>📄 security_provider.py: SecurityProvider, execute, verify_password"]
    class app_application_ports port
    app_application --> app_application_ports
    app_utils["<b>utils</b><br/><hr/>📄 helpers.py: setup_logging, ensure_directory, sanitize_filename<br/>📄 document_store.py: DocumentStore, read, write<br/>📄 jrvs_codec.py: JrvsDecodeError, encode, decode"]
    class app_utils support
    app --> app_utils
    app_domain["<b>domain</b>"]
    class app_domain support
    app --> app_domain
    app_domain_context["<b>context</b><br/><hr/>📄 context_manager.py: SystemContext, ContextManager"]
    class app_domain_context support
    app_domain --> app_domain_context
    app_domain_capabilities["<b>capabilities</b><br/><hr/>📄 cap_093.py: Cap093, execute<br/>📄 cap_061.py: Cap061, execute<br/>📄 cap_079.py: Cap079, execute<br/>📄 cap_067.py: Cap067, configure<br/>📄 cap_055.py: Cap055, execute<br/>📄 cap_058.py: Cap058, execute<br/>📄 cap_088.py: Cap088, execute<br/>📄 cap_078.py: Cap078, execute<br/>📄 cap_084.py: Cap084, execute<br/>📄 cap_073.py: Cap073, execute<br/>📄 cap_095.py: Cap095, configure<br/>📄 cap_070.py: Cap070, execute<br/>📄 cap_039.py: Cap039, configure<br/>📄 cap_100.py: Cap100, configure<br/>📄 cap_012.py: Cap012, execute<br/>📄 cap_040.py: Cap040, configure<br/>📄 cap_029.py: Cap029, execute<br/>📄 cap_101.py: Cap101, execute<br/>📄 cap_064.py: Cap064, execute<br/>📄 cap_063.py: Cap063, execute<br/>📄 cap_019.py: Cap019, execute<br/>📄 cap_054.py: Cap054, execute<br/>📄 cap_076.py: Cap076, execute<br/>📄 cap_065.py: Cap065, execute<br/>📄 cap_081.py: Cap081, execute<br/>📄 cap_022.py: Cap022, execute<br/>📄 cap_090.py: Cap090, execute<br/>📄 cap_048.py: Cap048, execute<br/>📄 cap_034.py: Cap034, configure<br/>📄 cap_069.py: Cap069, execute<br/>📄 cap_044.py: Cap044, configure<br/>📄 cap_021.py: Cap021, execute<br/>📄 cap_030.py: Cap030, execute<br/>📄 cap_083.py: Cap083, execute<br/>📄 cap_007.py: Cap007, configure<br/>📄 cap_089.py: Cap089, execute<br/>📄 cap_028.py: Cap028, execute<br/>📄 cap_059.py: Cap059, configure<br/>📄 cap_003.py: Cap003, configure<br/>📄 cap_002.py: Cap002, configure<br/>📄 cap_009.py: Cap009, execute<br/>📄 cap_049.py: Cap049, execute<br/>📄 cap_013.py: Cap013, execute<br/>📄 cap_047.py: Cap047, configure<br/>📄 cap_016.py: Cap016, execute<br/>📄 cap_060.py: Cap060, execute<br/>📄 cap_071.py: Cap071, execute<br/>📄 cap_001.py: Cap001, configure<br/>📄 cap_041.py: Cap041, execute<br/>📄 cap_010.py: Cap010, execute<br/>📄 cap_082.py: Cap082, execute<br/>📄 cap_092.py: Cap092, execute<br/>📄 cap_102.py: Cap102, execute<br/>📄 cap_045.py: Cap045, configure<br/>📄 cap_015.py: Cap015, execute<br/>📄 cap_062.py: Cap062, execute<br/>📄 cap_017.py: Cap017, execute<br/>📄 cap_005.py: Cap005, configure<br/>📄 cap_031.py: Cap031, execute<br/>📄 cap_086.py: Cap086, execute<br/>📄 cap_072.py: Cap072, configure<br/>📄 cap_032.py: Cap032, configure<br/>📄 cap_051.py: Cap051, execute<br/>📄 cap_026.py: Cap026, execute<br/>📄 cap_098.py: Cap098, execute<br/>📄 cap_033.py: Cap033, configure<br/>📄 cap_020.py: Cap020, execute<br/>📄 cap_075.py: Cap075, execute<br/>📄 cap_042.py: Cap042, execute<br/>📄 cap_018.py: Cap018, execute<br/>📄 cap_080.py: Cap080, execute<br/>📄 cap_085.py: Cap085, execute<br/>📄 cap_052.py: Cap052, execute<br/>📄 cap_077.py: Cap077, execute<br/>📄 context_memory.py: ContextMemory, configure, execute<br/>📄 cap_008.py: Cap008, configure<br/>📄 cap_068.py: Cap068, execute<br/>📄 cap_053.py: Cap053, execute<br/>📄 cap_043.py: Cap043, execute<br/>📄 cap_006.py: Cap006, configure<br/>📄 cap_035.py: Cap035, execute<br/>📄 cap_091.py: Cap091, execute<br/>📄 cap_023.py: Cap023, configure<br/>📄 cap_096.py: Cap096, execute<br/>📄 cap_074.py: Cap074, execute<br/>📄 cap_050.py: Cap050, execute<br/>📄 cap_014.py: Cap014, execute<br/>📄 cap_087.py: Cap087, execute<br/>📄 cap_011.py: Cap011, execute<br/>📄 cap_099.py: Cap099, execute<br/>📄 cap_037.py: Cap037, execute<br/>📄 cap_056.py: Cap056, execute<br/>📄 cap_097.py: Cap097, execute<br/>📄 cap_046.py: Cap046, execute<br/>📄 cap_038.py: Cap038, execute<br/>📄 cap_066.py: Cap066, execute<br/>📄 cap_025.py: Cap025, execute<br/>📄 cap_004.py: Cap004, configure<br/>📄 cap_057.py: Cap057, configure<br/>📄 cap_024.py: Cap024, execute<br/>📄 cap_027.py: Cap027, configure<br/>📄 cap_094.py: Cap094, execute<br/>📄 cap_036.py: Cap036, execute"]
    class app_domain_capabilities support
    app_domain --> app_domain_capabilities
    app_domain_services["<b>services</b><br/><hr/>📄 system_state_tracker.py: SystemStateTracker, execute<br/>📄 vocal_orchestrator.py: VocalOrchestrator, execute<br/>📄 intent_processor.py: IntentProcessor, can_execute, execute<br/>📄 agent_service.py: AgentService, execute<br/>📄 state_manager.py: StateManager, execute<br/>📄 reward_signal_provider.py: RewardSignalProvider, calculate_reward<br/>📄 command_interpreter.py: CommandInterpreter, execute<br/>📄 soldier_shield.py: SoldierShield, execute<br/>📄 safety_guardian.py: SafetyGuardian, configure<br/>📄 llm_command_interpreter.py: LLMCommandInterpreter, execute"]
    class app_domain_services support
    app_domain --> app_domain_services
    app_domain_gears["<b>gears</b><br/><hr/>📄 cognitive_router.py: CognitiveRouter, configure<br/>📄 llm_engine.py: LlmEngine, configure"]
    class app_domain_gears support
    app_domain --> app_domain_gears
    app_domain_orchestration["<b>orchestration</b><br/><hr/>📄 central_orchestrator.py: CentralOrchestrator, execute"]
    class app_domain_orchestration support
    app_domain --> app_domain_orchestration
    app_domain_missions["<b>missions</b><br/><hr/>📄 mission_selector.py: MissionSelector, execute"]
    class app_domain_missions support
    app_domain --> app_domain_missions
    app_domain_memory["<b>memory</b><br/><hr/>📄 semantic_memory.py: SemanticMemory, configure<br/>📄 working_memory.py: WorkingMemoryEntry, WorkingMemory<br/>📄 prospective_memory.py: ProspectiveMemory"]
    class app_domain_memory support
    app_domain --> app_domain_memory
    app_domain_analysis["<b>analysis</b><br/><hr/>📄 performance_analyzer.py: PerformanceAnalyzer, execute"]
    class app_domain_analysis support
    app_domain --> app_domain_analysis
    app_domain_ai["<b>ai</b><br/><hr/>📄 gemini_service.py: GeminiService, execute"]
    class app_domain_ai support
    app_domain --> app_domain_ai
    app_domain_ports["<b>ports</b><br/><hr/>📄 device_control_port.py: from, class, DeviceControlPort"]
    class app_domain_ports port
    app_domain --> app_domain_ports
    app_domain_models["<b>models</b><br/><hr/>📄 command.py: CommandType, Intent<br/>📄 system_state.py: SystemStatus, execute, Config<br/>📄 thought_log.py: InteractionStatus, ThoughtLog, Config<br/>📄 mission.py: class, execute, to_dict<br/>📄 device.py: Device, execute, Capability<br/>📄 adapter_registry.py: class, to_dict, AdapterRegistry<br/>📄 evolution_reward.py: EvolutionReward, execute<br/>📄 soldier.py: SoldierStatus, SoldierRegistration, soldier_id_not_empty<br/>📄 agent.py: ActionType, TaskSource, TaskPriority<br/>📄 capability.py: JarvisCapability, execute<br/>📄 viability.py: RiskLevel, ImpactLevel, class"]
    class app_domain_models support
    app_domain --> app_domain_models
    app_adapters["<b>adapters</b>"]
    class app_adapters adapter
    app --> app_adapters
    app_adapters_infrastructure["<b>infrastructure</b><br/><hr/>📄 setup_wizard.py: Colors, execute, print_header<br/>📄 playwright_worker.py: PlaywrightWorker, start<br/>📄 github_workflow_adapter.py: GitHubWorkflowAdapter, execute<br/>📄 overwatch_context.py: ContextMonitor, check_changes<br/>📄 gemini_context_manager.py: GeminiContextManager, execute<br/>📄 cost_tracker_adapter.py: CostTrackerAdapter<br/>📄 overwatch_adapter.py: OverwatchDaemon, execute<br/>📄 socket_client.py: SocketClient, execute<br/>📄 auto_repair_mixin.py: AutoRepairMixin, must, execute<br/>📄 github_correction_adapter.py: GitHubCorrectionAdapter<br/>📄 ai_gateway.py: AIGateway, groq_model<br/>📄 websocket_manager.py: WebSocketManager, execute<br/>📄 overwatch_resource_monitor.py: from, ResourceReading, ResourceMonitor<br/>📄 overwatch_daemon.py: OverwatchDaemon, execute<br/>📄 audit_logger.py: AuditLogger, configure, execute<br/>📄 ollama_adapter.py: OllamaAdapter, configure<br/>📄 persistent_shell_adapter.py: PersistentShellAdapter, configure<br/>📄 sqlite_history_adapter.py: Interaction, execute, SQLiteHistoryAdapter<br/>📄 jrvs_cloud_storage.py: JrvsCloudStorage, configure<br/>📄 consolidator.py: NexusComponent, Consolidator<br/>📄 mqtt_home_adapter.py: MqttHomeAdapter, execute<br/>📄 api_server.py: ChatRequest, create_api_server, health<br/>📄 docker_sandbox.py: DockerSandbox, run_tests<br/>📄 gemini_response_helpers.py: build_context_message, build_parameters, convert_function_call_to_intent<br/>📄 github_issue_mixin.py: GitHubIssueMixin, provides, execute<br/>📄 supabase_client.py: get_supabase_client, is_supabase_available<br/>📄 dummy_voice_provider.py: DummyVoiceProvider, execute<br/>📄 soldier_bridge.py: SoldierBridgeManager, connect<br/>📄 auth_adapter.py: AuthAdapter, execute<br/>📄 telegram_adapter.py: TelegramAdapter, can_execute<br/>📄 ai_gateway_token_utils.py: count_tokens, TokenCounter<br/>📄 vision_adapter.py: ExternalVisionNotAllowedError, VisionAdapter<br/>📄 pyinstaller_builder.py: PyinstallerBuilder, configure, can_execute<br/>📄 gist_uploader.py: GistUploader, can_execute<br/>📄 ai_gateway_enums.py: LLMProvider, GroqGear, AIGatewayEnums<br/>📄 gateway_llm_adapter.py: GatewayLLMCommandAdapter, get_system_instruction<br/>📄 http_client.py: HttpClient, request<br/>📄 overwatch_inactivity.py: InactivityMonitor, reset_timer<br/>📄 github_adapter.py: GitHubAdapter<br/>📄 overwatch_perimeter.py: PerimeterMonitor, to, execute<br/>📄 copilot_context_provider.py: GitHubCopilotContextProvider, execute, analyzes<br/>📄 api_models.py: RequestSource, RequestMetadata, ExecuteRequest<br/>📄 gemini_adapter.py: LLMCommandAdapter, execute<br/>📄 system_executor.py: SystemExecutor, configure, can_execute<br/>📄 reward_adapter.py: RewardAdapter, execute<br/>📄 github_issue_adapter.py: GitHubIssueAdapter, execute<br/>📄 action_provider.py: ActionProvider, execute<br/>📄 reward_logger.py: RewardLogger, execute<br/>📄 drive_uploader.py: DriveUploader, can_execute"]
    class app_adapters_infrastructure adapter
    app_adapters --> app_adapters_infrastructure
    app_adapters_infrastructure_secrets["<b>secrets</b><br/><hr/>📄 env_secrets_provider.py: EnvSecretsProvider, execute, get_secret"]
    class app_adapters_infrastructure_secrets adapter
    app_adapters_infrastructure --> app_adapters_infrastructure_secrets
    app_adapters_infrastructure_osint["<b>osint</b><br/><hr/>📄 eagle_osint_adapter.py: EagleOsintAdapter"]
    class app_adapters_infrastructure_osint adapter
    app_adapters_infrastructure --> app_adapters_infrastructure_osint
    app_adapters_infrastructure_routers["<b>routers</b><br/><hr/>📄 assistant.py: create_assistant_router<br/>📄 dev_agent.py: create_dev_agent_router, run_dev_agent, list_dev_agent_jobs<br/>📄 missions.py: create_missions_router, execute_mission, control_browser<br/>📄 thoughts.py: create_thoughts_router, create_thought_log<br/>📄 github.py: create_github_router, github_worker_operation, auto_heal_ci_failure<br/>📄 utility.py: create_utility_router, get_api_key_guides, analyze_missing_resources<br/>📄 bridge.py: create_bridge_router, local_bridge_websocket, list_connected_devices<br/>📄 devices.py: create_devices_router, register_device<br/>📄 evolution.py: create_evolution_router, get_evolution_status<br/>📄 health.py: create_health_router, health_check, health_detail<br/>📄 extensions.py: create_extensions_router, install_package, get_package_status"]
    class app_adapters_infrastructure_routers adapter
    app_adapters_infrastructure --> app_adapters_infrastructure_routers
    app_adapters_edge["<b>edge</b><br/><hr/>📄 macrodroid_adapter.py: MacroDroidAdapter, configure<br/>📄 automation_adapter.py: AutomationAdapter, execute<br/>📄 security_audit_adapter.py: TacticalCommandPort, NearbyDevice<br/>📄 combined_voice_provider.py: CombinedVoiceProvider, execute<br/>📄 active_recruiter_adapter.py: ActiveRecruiterAdapter, execute<br/>📄 voice_engine.py: JarvisEngine, execute<br/>📄 voice_adapter.py: VoiceAdapter, execute<br/>📄 web_adapter.py: WebAdapter, execute<br/>📄 keyboard_adapter.py: KeyboardAdapter, execute, type_text<br/>📄 worker_pc.py: main<br/>📄 hardware_controller.py: HardwareController, execute<br/>📄 jarvis_local_agent.py: JarvisLocalAgent, execute<br/>📄 tts_adapter.py: TTSAdapter, execute"]
    class app_adapters_edge adapter
    app_adapters --> app_adapters_edge
    app_adapters_api["<b>api</b><br/><hr/>📄 voice_endpoint.py: voice_stream"]
    class app_adapters_api adapter
    app_adapters --> app_adapters_api
    app_plugins["<b>plugins</b><br/><hr/>📄 plugin_loader.py: PluginLoader, execute"]
    class app_plugins support
    app --> app_plugins
    app_plugins_dynamic["<b>dynamic</b><br/><hr/>📄 example_plugin.py: hello_jarvis, register, PluginCapability"]
    class app_plugins_dynamic support
    app_plugins --> app_plugins_dynamic
    app_runtime["<b>runtime</b><br/><hr/>📄 pipeline_runner.py: CloudMock, run_pipeline"]
    class app_runtime support
    app --> app_runtime
    app_ports["<b>ports</b><br/><hr/>📄 voice_port.py: VoicePort, stt, tts<br/>📄 secrets_provider.py: SecretsProvider, get_secret"]
    class app_ports port
    app --> app_ports
    app_core["<b>core</b><br/><hr/>📄 nexus.py: JarvisNexus<br/>📄 encryption.py: get_hardware_id, derive_key_from_hardware, encrypt_value<br/>📄 nexus_exceptions.py: ImportTimeoutError, InstantiateTimeoutError, instantiation<br/>📄 nexus_registry.py: JrvsDecodeError<br/>📄 nexus_discovery.py: search_component_in_files, find_component_file<br/>📄 config.py: Settings, decrypt_api_key, decrypt_database_url<br/>📄 nexuscomponent.py: NexusComponent<br/>📄 llm_config.py: LLMConfig, use_llm_command_interpretation, use_llm_capability_detection"]
    class app_core core
    app --> app_core
    app_core_meta["<b>meta</b><br/><hr/>📄 compile_lock.py: acquire_compile_lock<br/>📄 jrvs_compiler.py: SchemaVersionError, JRVSCompiler<br/>📄 exploration_controller.py: ExplorationController, execute<br/>📄 decision_engine.py: class, DecisionEngine<br/>📄 policy_store.py: PolicyStore, get_policies_by_module"]
    class app_core_meta core
    app_core --> app_core_meta
    _backups["<b>.backups</b>"]
    class _backups support
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
    _backups_nexus_20260310_160218_app_adapters_infrastructure["<b>infrastructure</b><br/><hr/>📄 api_server.py: get_current_user, create_api_server, telegram_webhook<br/>📄 gateway_llm_adapter.py: GatewayLLMCommandAdapter, get_system_instruction<br/>📄 github_adapter.py: GitHubAdapter, execute"]
    class _backups_nexus_20260310_160218_app_adapters_infrastructure adapter
    _backups_nexus_20260310_160218_app_adapters --> _backups_nexus_20260310_160218_app_adapters_infrastructure
    _backups_nexus_20260310_160218_app_adapters_infrastructure_routers["<b>routers</b><br/><hr/>📄 github.py: create_github_router, github_worker_operation, auto_heal_ci_failure<br/>📄 evolution.py: create_evolution_router, get_evolution_status"]
    class _backups_nexus_20260310_160218_app_adapters_infrastructure_routers adapter
    _backups_nexus_20260310_160218_app_adapters_infrastructure --> _backups_nexus_20260310_160218_app_adapters_infrastructure_routers
    _backups_nexus_20260310_160218_app_adapters_edge["<b>edge</b><br/><hr/>📄 worker_pc.py: main"]
    class _backups_nexus_20260310_160218_app_adapters_edge adapter
    _backups_nexus_20260310_160218_app_adapters --> _backups_nexus_20260310_160218_app_adapters_edge
    _backups_cleanup["<b>cleanup</b>"]
    class _backups_cleanup support
    _backups --> _backups_cleanup
    data["<b>data</b>"]
    class data support
    data_jrvs["<b>jrvs</b>"]
    class data_jrvs support
    data --> data_jrvs
    migrations["<b>migrations</b>"]
    class migrations support
    requirements["<b>requirements</b>"]
    class requirements support
```
